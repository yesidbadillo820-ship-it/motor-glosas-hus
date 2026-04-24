"""Métricas de autopilot: cuántas glosas cerró la IA sola (Ronda 32).

Un endpoint que responde la pregunta clave del gestor para la capacitación:
«¿cuántas glosas se cerraron sin que el auditor las tocara?».

Criterio de 'cerrada por la IA':
  - modelo_ia LIKE '%texto_fijo%' OR modelo_ia LIKE '%pre-analisis%'
    (pre-rellenado por el scheduler de Ronda 2, Ronda 21 o el match
    perfecto de tarifa)

El endpoint devuelve:
  - hoy / semana / mes: conteos + sumatoria de valor_objetado
  - desglose por tipo: tarifa_match, texto_fijo/RATIFICADA, texto_fijo/EXTEMPORANEA
  - ahorro_estimado_tokens: N * 8000 (tokens ahorrados)
  - ahorro_estimado_usd: N * 0.012 ($12 por millón con Anthropic Sonnet)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import GlosaRecord


Periodo = Literal["hoy", "semana", "mes"]

# Aproximaciones pragmáticas — basadas en el prompt user típico (~6k tokens
# input + 2k output) y el precio Anthropic claude-sonnet-4 ($3 in / $15 out
# por millón). Un análisis completo cuesta ~0.012 USD.
TOKENS_POR_ANALISIS = 8000
USD_POR_ANALISIS = 0.012


def _desde(periodo: Periodo) -> datetime:
    ahora = datetime.now(timezone.utc)
    if periodo == "hoy":
        return ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    if periodo == "semana":
        return ahora - timedelta(days=7)
    return ahora - timedelta(days=30)


def metricas_autopilot(db: Session, periodo: Periodo = "hoy") -> dict:
    desde = _desde(periodo)

    def _contar(q_filter):
        q = (
            db.query(
                func.count(GlosaRecord.id).label("n"),
                func.coalesce(func.sum(GlosaRecord.valor_objetado), 0).label("v"),
            )
            .filter(GlosaRecord.creado_en >= desde)
        )
        q = q_filter(q)
        row = q.first()
        return (int(row.n or 0), float(row.v or 0.0)) if row else (0, 0.0)

    n_tarifa, v_tarifa = _contar(
        lambda q: q.filter(GlosaRecord.modelo_ia == "pre-analisis/texto_fijo")
    )
    n_ratif, v_ratif = _contar(
        lambda q: q.filter(GlosaRecord.modelo_ia.ilike("%texto_fijo/RATIFICADA%"))
    )
    n_exte, v_exte = _contar(
        lambda q: q.filter(GlosaRecord.modelo_ia.ilike("%texto_fijo/EXTEMPORANEA%"))
    )

    total_n = n_tarifa + n_ratif + n_exte
    total_v = v_tarifa + v_ratif + v_exte

    # Glosas totales creadas en el periodo (para el %)
    total_periodo = (
        db.query(func.count(GlosaRecord.id))
        .filter(GlosaRecord.creado_en >= desde)
        .scalar() or 0
    )
    pct = round(float(total_n) / float(total_periodo), 3) if total_periodo else 0.0

    return {
        "periodo": periodo,
        "desde": desde.isoformat(),
        "cerradas_por_ia": {
            "total": total_n,
            "valor_objetado": total_v,
            "pct_sobre_creadas": pct,
        },
        "desglose": {
            "tarifa_match_perfecto": {"cantidad": n_tarifa, "valor": v_tarifa},
            "texto_fijo_ratificada": {"cantidad": n_ratif, "valor": v_ratif},
            "texto_fijo_extemporanea": {"cantidad": n_exte, "valor": v_exte},
        },
        "ahorro": {
            "tokens_estimados": total_n * TOKENS_POR_ANALISIS,
            "usd_estimados": round(total_n * USD_POR_ANALISIS, 2),
            "horas_ahorradas_aprox": round(total_n * 3 / 60, 1),  # 3min por glosa manual
        },
        "total_creadas_periodo": total_periodo,
    }
