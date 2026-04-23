"""Predictor de glosas — evalúa el riesgo de que una factura sea glosada
antes de radicarla ante la EPS.

Ronda 4 de la visión premium. Usa SOLO el histórico del sistema + reglas
determinísticas (sin llamar a IA). Da al equipo de facturación un
semáforo con: probabilidad de glosa, códigos probables, motivos, y
recomendaciones para reducir el riesgo.

Input (dict):
  - eps: nombre EPS / pagador
  - cups: código CUPS
  - valor_facturado: float
  - tipo_servicio: opcional (hospitalario, ambulatorio, urgencia)
  - tiene_autorizacion: bool (si aplica)
  - tiene_historia_clinica: bool

Output:
  {
    "probabilidad_glosa": 0.0–1.0,
    "nivel_riesgo": "BAJO" | "MEDIO" | "ALTO" | "CRÍTICO",
    "codigos_probables": [{"codigo": "TA0201", "prob": 0.45}],
    "motivos": [str],
    "recomendaciones": [str],
    "valor_en_riesgo": float,  # valor × prob
  }

Aprende del histórico: cuántas veces esa combinación (eps, cups) resultó
en glosa real, qué códigos salieron, cuánto se objetó en promedio.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import GlosaRecord


def _normalizar_eps(eps: str) -> str:
    return (eps or "").strip().upper()


def _buscar_tarifa_pactada(db: Session, eps: str, cups: str) -> Optional[dict]:
    """Consulta si hay tarifa pactada en tarifas_contratadas."""
    try:
        from app.services.tarifa_lookup_service import evaluar_glosa_tarifa
        info = evaluar_glosa_tarifa(
            db, eps=eps, cups=cups, valor_facturado=0.0, valor_objetado=0.0,
        )
        if info.get("encontrada"):
            return info.get("tarifa")
    except Exception:
        pass
    return None


def predecir_glosa(
    db: Session,
    eps: str,
    cups: str,
    valor_facturado: float = 0.0,
    tipo_servicio: str = "",
    tiene_autorizacion: bool = True,
    tiene_historia_clinica: bool = True,
    tiene_soportes: bool = True,
) -> dict:
    """Predice riesgo de glosa para una combinación (eps, cups, valor)."""
    eps_u = _normalizar_eps(eps)
    cups = (cups or "").strip()
    valor_facturado = float(valor_facturado or 0.0)

    # 1) Histórico: cuántas facturas con (eps, cups) han sido glosadas
    hace_12m = datetime.utcnow() - timedelta(days=365)
    try:
        total_hist = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.eps.ilike(f"%{eps_u}%"))
            .filter(GlosaRecord.cups_servicio == cups)
            .filter(GlosaRecord.creado_en >= hace_12m)
            .scalar() or 0
        )
    except Exception:
        total_hist = 0

    # 2) Total de facturas con mismo CUPS (independiente de EPS) para dar contexto
    try:
        total_cups = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.cups_servicio == cups)
            .filter(GlosaRecord.creado_en >= hace_12m)
            .scalar() or 0
        )
    except Exception:
        total_cups = 0

    # 3) Códigos de glosa más comunes para esta combinación
    codigos_probables = []
    try:
        top_codigos = (
            db.query(
                GlosaRecord.codigo_glosa,
                func.count(GlosaRecord.id).label("n"),
            )
            .filter(GlosaRecord.eps.ilike(f"%{eps_u}%"))
            .filter(GlosaRecord.cups_servicio == cups)
            .filter(GlosaRecord.creado_en >= hace_12m)
            .group_by(GlosaRecord.codigo_glosa)
            .order_by(func.count(GlosaRecord.id).desc())
            .limit(3)
            .all()
        )
        base_total = sum(n for _, n in top_codigos) or 1
        codigos_probables = [
            {
                "codigo": cod or "(sin código)",
                "prob": round(n / base_total, 2),
                "ocurrencias": int(n),
            }
            for cod, n in top_codigos if cod
        ]
    except Exception:
        pass

    # 4) Cálculo del score base (0.0 - 1.0)
    score = 0.0
    motivos: list[str] = []
    recomendaciones: list[str] = []

    # Histórico: si hay muchos casos previos con glosa → sube score
    if total_hist >= 10:
        score += 0.35
        motivos.append(
            f"Histórico: {total_hist} glosas previas en esta combinación EPS+CUPS (últimos 12m)."
        )
    elif total_hist >= 3:
        score += 0.20
        motivos.append(f"Histórico moderado: {total_hist} glosas previas.")
    elif total_hist > 0:
        score += 0.10
        motivos.append(f"Histórico bajo: {total_hist} glosa previa.")

    # Si el CUPS es muy glosado en general (>5% de todas las glosas)
    if total_cups >= 20:
        score += 0.15
        motivos.append(f"CUPS frecuentemente glosado ({total_cups} casos totales).")

    # Sin tarifa pactada con la EPS → riesgo de TA alto
    tarifa = _buscar_tarifa_pactada(db, eps_u, cups)
    if not tarifa:
        score += 0.15
        motivos.append(
            "No hay tarifa pactada en el contrato para esta combinación EPS+CUPS."
        )
        recomendaciones.append(
            "Cargar el valor oficial del contrato en /tarifas para evitar TA0201."
        )
    else:
        motivos.append(
            f"Tarifa pactada encontrada: contrato {tarifa.get('contrato_numero','—')}."
        )

    # Valor facturado alto → riesgo de revisión manual EPS (>$1M)
    if valor_facturado >= 1_000_000:
        score += 0.10
        motivos.append(
            f"Valor facturado alto (${valor_facturado:,.0f}), revisión manual probable."
        )
    if valor_facturado >= 5_000_000:
        score += 0.10
        motivos.append("Valor > $5M: alta probabilidad de auditoría específica.")

    # Falta de soportes / autorización / HC
    if not tiene_autorizacion:
        score += 0.12
        motivos.append("Sin autorización previa registrada.")
        recomendaciones.append("Adjuntar autorización de la EPS o justificar urgencia.")
    if not tiene_historia_clinica:
        score += 0.10
        motivos.append("Sin referencia a historia clínica.")
        recomendaciones.append("Referenciar número de historia clínica institucional.")
    if not tiene_soportes:
        score += 0.08
        motivos.append("Sin soportes documentales adjuntos.")
        recomendaciones.append("Adjuntar RIPS + factura electrónica + HC relevantes.")

    # Tipo de servicio: urgencias suelen glosarse menos si hay HC
    if "URGENCIA" in (tipo_servicio or "").upper() and tiene_historia_clinica:
        score -= 0.08
        motivos.append("Urgencia con HC: menos riesgo de cobertura (T-1025/2002).")

    # Normalizar score a [0, 1]
    score = max(0.0, min(1.0, score))

    # Nivel
    if score >= 0.65:
        nivel = "CRÍTICO"
    elif score >= 0.45:
        nivel = "ALTO"
    elif score >= 0.25:
        nivel = "MEDIO"
    else:
        nivel = "BAJO"

    # Recomendaciones adicionales por nivel
    if nivel in ("ALTO", "CRÍTICO"):
        recomendaciones.append(
            "Considerar enviar a revisión interna antes de radicar (disminuye ratificación)."
        )
    if nivel == "CRÍTICO":
        recomendaciones.append(
            "Validar contrato + soportes + autorización ANTES de radicar. "
            "Opcional: convocar a mesa preventiva con la EPS."
        )

    return {
        "probabilidad_glosa": round(score, 3),
        "nivel_riesgo": nivel,
        "codigos_probables": codigos_probables,
        "motivos": motivos,
        "recomendaciones": recomendaciones,
        "valor_en_riesgo": round(valor_facturado * score, 2),
        "historico_12m": {
            "glosas_eps_cups": total_hist,
            "glosas_cups_total": total_cups,
        },
        "tarifa_pactada_encontrada": bool(tarifa),
    }
