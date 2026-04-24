"""Digest ejecutivo diario/semanal (Ronda 19).

Consolida la data que el coordinador necesita cada mañana en un único
objeto listo para ser enviado por email, WhatsApp o Telegram:

  - Indicadores del día/semana (recuperado, objetado, tasa_recuperacion)
  - Contadores operativos (pendientes, vencidas, críticas <48h)
  - Conteo por estado autopilot (LISTA_ENVIAR, INTERVENIR, etc.)
  - Top 3 EPS del periodo
  - Alertas críticas (estado_general + lista consolidada)

Dos APIs:
  - generar_digest(db, periodo='dia'|'semana') → dict estructurado
  - formatear_digest_texto(digest) → string multilinea listo para bot
  - formatear_digest_html(digest) → HTML listo para email

Es pasivo: no envía nada por sí mismo. Para envío, el router o un
scheduler externo invoca bot_mensajeria.enviar_notificacion().
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import GlosaRecord
from app.services.autopilot_service import ESTADOS, evaluar_bandeja
from app.services.health_monitor import checar_salud


Periodo = Literal["dia", "semana", "mes"]


def _ventana(periodo: Periodo) -> tuple[datetime, datetime]:
    ahora = datetime.now(timezone.utc)
    if periodo == "dia":
        desde = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    elif periodo == "semana":
        desde = ahora - timedelta(days=7)
    else:
        desde = ahora - timedelta(days=30)
    return desde, ahora


def _top_eps(db: Session, desde: datetime, hasta: datetime, n: int = 3) -> list[dict]:
    rows = (
        db.query(
            GlosaRecord.eps,
            func.count(GlosaRecord.id).label("cantidad"),
            func.coalesce(func.sum(GlosaRecord.valor_objetado), 0).label("valor"),
        )
        .filter(GlosaRecord.creado_en >= desde, GlosaRecord.creado_en <= hasta)
        .group_by(GlosaRecord.eps)
        .order_by(func.count(GlosaRecord.id).desc())
        .limit(n)
        .all()
    )
    return [
        {
            "eps": r.eps or "N/A",
            "cantidad": int(r.cantidad or 0),
            "valor_objetado": float(r.valor or 0.0),
        }
        for r in rows
    ]


def generar_digest(db: Session, periodo: Periodo = "dia") -> dict:
    """Arma el digest completo del periodo indicado."""
    desde, hasta = _ventana(periodo)

    # Salud consolidada (reusa Ronda 17)
    salud = checar_salud(db)

    # Indicadores del periodo
    total_obj = (
        db.query(func.coalesce(func.sum(GlosaRecord.valor_objetado), 0))
        .filter(GlosaRecord.creado_en >= desde, GlosaRecord.creado_en <= hasta)
        .scalar() or 0.0
    )
    total_rec = (
        db.query(func.coalesce(func.sum(GlosaRecord.valor_recuperado), 0))
        .filter(GlosaRecord.fecha_decision_eps >= desde, GlosaRecord.fecha_decision_eps <= hasta)
        .scalar() or 0.0
    )
    cantidad_radicadas = (
        db.query(func.count(GlosaRecord.id))
        .filter(GlosaRecord.creado_en >= desde, GlosaRecord.creado_en <= hasta)
        .scalar() or 0
    )
    cantidad_respondidas = (
        db.query(func.count(GlosaRecord.id))
        .filter(GlosaRecord.fecha_decision_eps >= desde, GlosaRecord.fecha_decision_eps <= hasta)
        .scalar() or 0
    )
    tasa_rec = (
        round(float(total_rec) / float(total_obj), 3)
        if total_obj and total_obj > 0 else 0.0
    )

    # Autopilot: conteo global de la bandeja PENDIENTE
    try:
        autopilot = evaluar_bandeja(db, auditor_email=None, limite=300)
        conteo_autopilot = autopilot.get("conteo_por_estado", {e: 0 for e in ESTADOS})
    except Exception:
        conteo_autopilot = {e: 0 for e in ESTADOS}

    # Top EPS del periodo
    top_eps = _top_eps(db, desde, hasta, n=3)

    return {
        "periodo": periodo,
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "estado_general": salud["estado_general"],
        "indicadores": {
            "radicadas": int(cantidad_radicadas),
            "respondidas": int(cantidad_respondidas),
            "valor_objetado": float(total_obj),
            "valor_recuperado": float(total_rec),
            "tasa_recuperacion": tasa_rec,
        },
        "operativo": {
            "pendientes_total": salud["componentes"]["glosas_hoy"].get("pendientes_total", 0),
            "vencidas": salud["componentes"]["glosas_hoy"].get("vencidas", 0),
        },
        "autopilot": conteo_autopilot,
        "top_eps": top_eps,
        "alertas": salud.get("alertas", []),
    }


def formatear_digest_texto(digest: dict) -> str:
    """Convierte el digest a texto plano para bots de mensajería."""
    ind = digest["indicadores"]
    op = digest["operativo"]
    ap = digest["autopilot"]
    lineas = [
        f"📊 RESUMEN {digest['periodo'].upper()} — estado: {digest['estado_general']}",
        "",
        f"• Radicadas: {ind['radicadas']}  · Respondidas: {ind['respondidas']}",
        f"• Objetado: ${int(ind['valor_objetado']):,}",
        f"• Recuperado: ${int(ind['valor_recuperado']):,} ({ind['tasa_recuperacion']*100:.1f}%)",
        f"• Pendientes: {op['pendientes_total']}  · Vencidas: {op['vencidas']}",
        "",
        f"🤖 Autopilot:",
        f"   LISTA_ENVIAR: {ap.get('LISTA_ENVIAR', 0)}",
        f"   CASI_LISTA:   {ap.get('CASI_LISTA', 0)}",
        f"   REVISAR:      {ap.get('REVISAR', 0)}",
        f"   INTERVENIR:   {ap.get('INTERVENIR', 0)}",
    ]
    if digest["top_eps"]:
        lineas.append("")
        lineas.append("🏆 Top EPS del periodo:")
        for i, e in enumerate(digest["top_eps"], 1):
            lineas.append(
                f"   {i}. {e['eps']}: {e['cantidad']} glosas, "
                f"${int(e['valor_objetado']):,}"
            )
    if digest.get("alertas"):
        lineas.append("")
        lineas.append("⚠️  Alertas:")
        for a in digest["alertas"][:5]:
            lineas.append(f"   [{a.get('nivel', '?')}] {a.get('mensaje', '')}")
    return "\n".join(lineas)


def formatear_digest_html(digest: dict) -> str:
    """Convierte el digest a HTML minimal listo para email."""
    ind = digest["indicadores"]
    op = digest["operativo"]
    ap = digest["autopilot"]
    top_eps_html = "".join(
        f"<li>{e['eps']}: {e['cantidad']} glosas · "
        f"${int(e['valor_objetado']):,}</li>"
        for e in digest["top_eps"]
    ) or "<li>—</li>"
    alertas_html = "".join(
        f"<li><b>[{a.get('nivel','?')}]</b> {a.get('mensaje','')}</li>"
        for a in digest.get("alertas", [])[:5]
    ) or "<li>Sin alertas activas.</li>"
    return (
        f"<h2>📊 Resumen {digest['periodo']}</h2>"
        f"<p>Estado general: <b>{digest['estado_general']}</b></p>"
        f"<ul>"
        f"<li>Radicadas: {ind['radicadas']} · Respondidas: {ind['respondidas']}</li>"
        f"<li>Objetado: ${int(ind['valor_objetado']):,}</li>"
        f"<li>Recuperado: ${int(ind['valor_recuperado']):,} "
        f"({ind['tasa_recuperacion']*100:.1f}%)</li>"
        f"<li>Pendientes: {op['pendientes_total']} · Vencidas: {op['vencidas']}</li>"
        f"</ul>"
        f"<h3>🤖 Autopilot</h3>"
        f"<ul>"
        f"<li>LISTA_ENVIAR: {ap.get('LISTA_ENVIAR',0)}</li>"
        f"<li>CASI_LISTA: {ap.get('CASI_LISTA',0)}</li>"
        f"<li>REVISAR: {ap.get('REVISAR',0)}</li>"
        f"<li>INTERVENIR: {ap.get('INTERVENIR',0)}</li>"
        f"</ul>"
        f"<h3>🏆 Top EPS</h3><ul>{top_eps_html}</ul>"
        f"<h3>⚠️ Alertas</h3><ul>{alertas_html}</ul>"
    )
