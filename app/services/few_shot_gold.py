"""Few-shot dinámico de dictámenes ganadores (R-cerebro mejora #2).

Inyecta 1-2 ejemplos de dictámenes que YA GANARON (estado = LEVANTADA o
plantilla curada en `plantillas_gold`) para el mismo par (eps,
codigo_glosa). El LLM aprende del estilo y argumentación que funcionó
con esa misma EPS y código.

Estrategia de búsqueda (en orden):
  1. PlantillaGoldRecord activa para (eps, codigo) — curado por equipo
  2. GlosaRecord con estado=LEVANTADA, mismo (eps, codigo), dictamen
     >= 200 chars, ordenado por fecha_decision_eps DESC
  3. Vacío si no hay ninguno

Filosofía:
  • Solo se inyectan si existen — no perturba el caso base sin histórico
  • Truncamos cada ejemplo a 1500 chars para no inflar el prompt
  • Marcamos claramente "EJEMPLO" para que el LLM no copie textual
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Límite de chars por ejemplo para no inflar el contexto
_MAX_CHARS_EJEMPLO = 1500
# Límite de ejemplos a inyectar
_MAX_EJEMPLOS = 2


def obtener_ejemplos_gold(
    db,
    eps: str,
    codigo: str,
    max_ejemplos: int = _MAX_EJEMPLOS,
) -> list[dict]:
    """Devuelve hasta N dictámenes ganadores del par (eps, codigo).

    Cada ejemplo: {"argumento": str, "fuente": "GOLD"|"HISTORICO", "id": int}
    """
    if not db or not eps or not codigo:
        return []
    eps_norm = (eps or "").strip()
    cod_norm = (codigo or "").strip().upper()
    if not eps_norm or not cod_norm:
        return []

    ejemplos: list[dict] = []

    # 1) PlantillaGoldRecord (curadas por el equipo jurídico)
    try:
        from app.models.db import PlantillaGoldRecord
        gold = (
            db.query(PlantillaGoldRecord)
            .filter(PlantillaGoldRecord.eps.ilike(eps_norm))
            .filter(PlantillaGoldRecord.codigo_glosa == cod_norm)
            .filter(PlantillaGoldRecord.activa == 1)
            .order_by(PlantillaGoldRecord.usos.desc())
            .limit(int(max_ejemplos))
            .all()
        )
        for g in gold:
            arg = (g.argumento or "").strip()
            if len(arg) < 200:
                continue
            ejemplos.append({
                "argumento": arg[:_MAX_CHARS_EJEMPLO],
                "fuente": "GOLD",
                "id": g.id,
            })
            if len(ejemplos) >= max_ejemplos:
                return ejemplos
        # Si encontramos AL MENOS un gold, NO mezclamos con histórico:
        # las plantillas curadas son por definición mejores referentes.
        if ejemplos:
            return ejemplos
    except Exception as e:
        logger.debug(f"few_shot_gold: error consultando PlantillaGold: {e}")

    # 2) Fallback: GlosaRecord LEVANTADA con dictamen útil
    try:
        from app.models.db import GlosaRecord
        rows = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.eps.ilike(eps_norm))
            .filter(GlosaRecord.codigo_glosa == cod_norm)
            .filter(GlosaRecord.estado == "LEVANTADA")
            .filter(GlosaRecord.dictamen.isnot(None))
            .order_by(GlosaRecord.fecha_decision_eps.desc())
            .limit(20)
            .all()
        )
        for r in rows:
            arg = (r.dictamen or "").strip()
            if len(arg) < 200:
                continue
            # Evitar duplicados: ya tenemos uno con este texto
            if any(arg[:200] == e["argumento"][:200] for e in ejemplos):
                continue
            ejemplos.append({
                "argumento": arg[:_MAX_CHARS_EJEMPLO],
                "fuente": "HISTORICO",
                "id": r.id,
            })
            if len(ejemplos) >= max_ejemplos:
                break
    except Exception as e:
        logger.debug(f"few_shot_gold: error consultando GlosaRecord: {e}")

    return ejemplos


def bloque_few_shot_para_prompt(ejemplos: list[dict]) -> str:
    """Construye el bloque de texto a anexar al user_prompt."""
    if not ejemplos:
        return ""

    partes = [
        "",
        "═══ EJEMPLOS DE DICTÁMENES GANADORES PREVIOS (mismo eps + código) ═══",
        (
            "Estos casos ANTERIORES ganaron la glosa (LEVANTADA). "
            "Úsalos como referencia de ESTILO Y ARGUMENTACIÓN, "
            "adaptándolos al caso ACTUAL con los datos del BLOQUE 1. "
            "NO copies textualmente."
        ),
        "",
    ]
    for i, ej in enumerate(ejemplos, 1):
        fuente = ej.get("fuente", "?")
        partes.append(f"--- EJEMPLO {i} (fuente: {fuente}) ---")
        partes.append(ej["argumento"])
        partes.append("--- FIN EJEMPLO ---")
        partes.append("")
    partes.append(
        "⚠ El dictamen final debe usar los DATOS DEL BLOQUE 1 (CUPS, valor, "
        "EPS exactos del caso actual), no los del ejemplo."
    )
    partes.append("═══════════════════════════════════════════════════════════════════")
    partes.append("")
    return "\n".join(partes)


def construir_bloque_gold(
    db, eps: str, codigo: str, max_ejemplos: int = _MAX_EJEMPLOS,
) -> str:
    """Helper de un solo paso: busca y formatea."""
    try:
        ejemplos = obtener_ejemplos_gold(db, eps, codigo, max_ejemplos)
        if ejemplos:
            logger.info(
                f"[FEW-SHOT-GOLD] {len(ejemplos)} ejemplo(s) inyectado(s) "
                f"para par ({eps}, {codigo})"
            )
        return bloque_few_shot_para_prompt(ejemplos)
    except Exception as e:
        logger.warning(f"few_shot_gold: error construyendo bloque: {e}")
        return ""
