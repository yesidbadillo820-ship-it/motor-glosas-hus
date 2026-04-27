"""Calibración del prompt por dificultad histórica del par (eps, código).

Mejora #3 del cerebro IA: en lugar de usar siempre el mismo nivel de
énfasis, ajustamos la "agresividad argumentativa" según cómo le ha ido
históricamente al HUS con esa combinación de EPS y código de glosa.

Lógica:
  - tasa ≥ 70% en N≥3 casos → caso FAVORABLE: tono confiado y conciso
  - tasa 40-70% → MEDIO: defensa estándar
  - tasa ≤ 30% → caso DIFÍCIL: argumentación extensa, normativa
    completa, blindaje anti-ratificación reforzado
  - sin histórico (N<3) → no inyecta hint
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Mínimo de muestras para calibrar (evita conclusiones de N=1)
_MIN_MUESTRAS = 3
# Umbrales
_UMBRAL_FAVORABLE = 70.0
_UMBRAL_DIFICIL = 30.0


def calcular_dificultad(
    db, eps: str, codigo: str,
) -> Optional[dict]:
    """Calcula la dificultad histórica del par.

    Retorna dict con tasa, n_muestras, n_levantadas y nivel
    (FAVORABLE / MEDIO / DIFICIL), o None si no hay datos.
    """
    if not db or not eps or not codigo:
        return None
    eps_norm = (eps or "").strip()
    cod_norm = (codigo or "").strip().upper()
    if not eps_norm or not cod_norm:
        return None

    try:
        from app.models.db import GlosaRecord
        rows = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.eps.ilike(eps_norm))
            .filter(GlosaRecord.codigo_glosa == cod_norm)
            .filter(GlosaRecord.estado.in_(
                ["LEVANTADA", "ACEPTADA", "RATIFICADA"],
            ))
            .all()
        )
    except Exception as e:
        logger.debug(f"calibracion_dificultad: error: {e}")
        return None

    n = len(rows)
    if n < _MIN_MUESTRAS:
        return None

    n_lev = sum(
        1 for r in rows
        if (r.estado or "").upper() == "LEVANTADA"
    )
    tasa = 100.0 * n_lev / n

    if tasa >= _UMBRAL_FAVORABLE:
        nivel = "FAVORABLE"
    elif tasa <= _UMBRAL_DIFICIL:
        nivel = "DIFICIL"
    else:
        nivel = "MEDIO"

    return {
        "tasa_pct": round(tasa, 2),
        "n_muestras": n,
        "n_levantadas": n_lev,
        "nivel": nivel,
    }


def bloque_calibracion_para_prompt(dif: Optional[dict]) -> str:
    """Construye el bloque a anexar al user_prompt según la dificultad."""
    if not dif:
        return ""

    nivel = dif["nivel"]
    tasa = dif["tasa_pct"]
    n = dif["n_muestras"]
    n_lev = dif["n_levantadas"]

    if nivel == "FAVORABLE":
        return (
            "\n[CALIBRACIÓN POR HISTORIAL]\n"
            f"  Histórico del par eps+código: {n_lev}/{n} levantadas ({tasa:.0f}%)\n"
            "  Caso HISTÓRICAMENTE FAVORABLE — la EPS suele ceder en este código.\n"
            "  • Tono CONCILIADOR DIRECTO. Argumentación clara y económica.\n"
            "  • Cita 2 normas core (no satures con 4-5).\n"
            "  • Cierre conciliador: invita a levantar sin escalar.\n"
        )
    elif nivel == "DIFICIL":
        return (
            "\n[CALIBRACIÓN POR HISTORIAL — MODO BLINDAJE REFORZADO]\n"
            f"  Histórico del par eps+código: {n_lev}/{n} levantadas ({tasa:.0f}%)\n"
            "  Caso HISTÓRICAMENTE DIFÍCIL — la EPS suele RATIFICAR este código.\n"
            "  • Defensa AMPLIADA con argumentación normativa extensa.\n"
            "  • Cita 3-4 normas con texto literal entre comillas (no 2).\n"
            "  • Incluye OBLIGATORIAMENTE 2 cláusulas anti-rebatimiento\n"
            "    en el párrafo 3 (NO PUEDE TRASLADARSE / NO SIENDO\n"
            "    PROCEDENTE / SIN QUE SEA ADMISIBLE).\n"
            "  • Anclaje probatorio explícito si hay PDF (folios, fechas,\n"
            "    médicos, diagnóstico).\n"
            "  • En el cierre, además de la mesa de conciliación, RESERVA\n"
            "    expresa de acudir a SuperSalud (Art. 126 Ley 1438/2011).\n"
        )
    else:  # MEDIO
        return (
            "\n[CALIBRACIÓN POR HISTORIAL]\n"
            f"  Histórico del par eps+código: {n_lev}/{n} levantadas ({tasa:.0f}%)\n"
            "  Caso de dificultad MEDIA — sin patrón claro.\n"
            "  • Defensa técnico-jurídica estándar.\n"
            "  • Cita 2-3 normas core, una con texto literal.\n"
            "  • Incluye 1 cláusula anti-rebatimiento.\n"
        )


def construir_bloque_calibracion(db, eps: str, codigo: str) -> str:
    """Helper de un solo paso: calcula y formatea."""
    try:
        dif = calcular_dificultad(db, eps, codigo)
        if dif:
            logger.info(
                f"[CALIBRACION] par ({eps}, {codigo}) → "
                f"{dif['nivel']} ({dif['tasa_pct']:.0f}% en {dif['n_muestras']} casos)"
            )
        return bloque_calibracion_para_prompt(dif)
    except Exception as e:
        logger.warning(f"calibracion_dificultad: error construyendo bloque: {e}")
        return ""
