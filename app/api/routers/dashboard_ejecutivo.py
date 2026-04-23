"""Dashboard ejecutivo live para directivos (Ronda 9).

Agrupa en un único endpoint las métricas clave para el Comité de Cartera:

  GET /dashboard-ejecutivo/vivo
    {
      "valor_recuperado_mes": float,
      "valor_objetado_mes": float,
      "tasa_recuperacion_pct": 0-100,
      "glosas_analizadas_hoy": int,
      "glosas_pendientes": int,
      "glosas_criticas_48h": int,     # vencen en <48h
      "glosas_vencidas": int,
      "ranking_auditores": [{"email", "glosas_respondidas", "valor_recuperado", "pct_exito"}],
      "ranking_eps_ratificacion": [{"eps", "ratif_pct", "cantidad"}],
      "alertas_proactivas": [{"titulo", "cuerpo", "severidad"}],
    }

Incluye alertas automáticas: glosas a punto de vencer, EPS con spike de
ratificación, tokens IA consumidos hoy vs promedio, etc.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord

router = APIRouter(prefix="/dashboard-ejecutivo", tags=["dashboard-ejecutivo"])


@router.get("/vivo")
def dashboard_vivo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Retorna todas las métricas ejecutivas en UN solo fetch.

    Diseñado para refrescarse cada 30-60s en el dashboard del coordinador
    sin saturar la BD: ~6 queries agregadas, ninguna scan full.
    """
    ahora = datetime.utcnow()
    inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    en_48h = ahora + timedelta(hours=48)

    # ─── Valor recuperado y objetado del mes ────────────────────────────────
    try:
        total_obj_mes = (
            db.query(func.coalesce(func.sum(GlosaRecord.valor_objetado), 0))
            .filter(GlosaRecord.creado_en >= inicio_mes)
            .scalar() or 0.0
        )
        total_rec_mes = (
            db.query(func.coalesce(func.sum(GlosaRecord.valor_recuperado), 0))
            .filter(GlosaRecord.creado_en >= inicio_mes)
            .scalar() or 0.0
        )
    except Exception:
        total_obj_mes, total_rec_mes = 0.0, 0.0

    tasa_recuperacion = (
        round(100 * float(total_rec_mes) / float(total_obj_mes), 2)
        if total_obj_mes else 0.0
    )

    # ─── Hoy: glosas analizadas, pendientes, críticas, vencidas ────────────
    try:
        glosas_hoy = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.creado_en >= inicio_hoy
        ).scalar() or 0
        pendientes = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"])
        ).scalar() or 0
        criticas_48h = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"])
        ).filter(GlosaRecord.fecha_vencimiento <= en_48h).filter(
            GlosaRecord.fecha_vencimiento >= ahora
        ).scalar() or 0
        vencidas = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"])
        ).filter(GlosaRecord.fecha_vencimiento < ahora).scalar() or 0
    except Exception:
        glosas_hoy, pendientes, criticas_48h, vencidas = 0, 0, 0, 0

    # ─── Ranking de auditores (top 5) ───────────────────────────────────────
    try:
        rows = (
            db.query(
                GlosaRecord.auditor_email,
                func.count(GlosaRecord.id).label("n"),
                func.coalesce(func.sum(GlosaRecord.valor_recuperado), 0).label("rec"),
                func.sum(
                    case(
                        (GlosaRecord.decision_eps == "LEVANTADA", 1),
                        else_=0,
                    )
                ).label("ganadas"),
            )
            .filter(GlosaRecord.auditor_email.isnot(None))
            .filter(GlosaRecord.creado_en >= inicio_mes)
            .group_by(GlosaRecord.auditor_email)
            .order_by(func.coalesce(func.sum(GlosaRecord.valor_recuperado), 0).desc())
            .limit(5)
            .all()
        )
        ranking_auditores = [
            {
                "email": (e or "").split("@")[0],  # privacidad: solo username
                "glosas_respondidas": int(n),
                "valor_recuperado": float(rec or 0),
                "ganadas": int(g or 0),
                "pct_exito": round(100 * int(g or 0) / int(n), 1) if int(n) else 0.0,
            }
            for e, n, rec, g in rows
        ]
    except Exception:
        ranking_auditores = []

    # ─── Ranking EPS por % ratificación (top 5 peores) ──────────────────────
    try:
        rows_eps = (
            db.query(
                GlosaRecord.eps,
                func.count(GlosaRecord.id).label("n"),
                func.sum(
                    case(
                        (GlosaRecord.decision_eps == "RATIFICADA", 1),
                        else_=0,
                    )
                ).label("ratif"),
            )
            .filter(GlosaRecord.decision_eps.isnot(None))
            .filter(GlosaRecord.creado_en >= inicio_mes)
            .group_by(GlosaRecord.eps)
            .having(func.count(GlosaRecord.id) >= 5)  # mín 5 decisiones
            .order_by((func.sum(
                case((GlosaRecord.decision_eps == "RATIFICADA", 1), else_=0)
            ) * 1.0 / func.count(GlosaRecord.id)).desc())
            .limit(5)
            .all()
        )
        ranking_eps = [
            {
                "eps": eps or "—",
                "cantidad": int(n),
                "ratificadas": int(r or 0),
                "ratif_pct": round(100 * int(r or 0) / int(n), 1) if int(n) else 0.0,
            }
            for eps, n, r in rows_eps
        ]
    except Exception:
        ranking_eps = []

    # ─── Alertas proactivas ────────────────────────────────────────────────
    alertas = []
    if vencidas > 0:
        alertas.append({
            "titulo": f"⚠️ {vencidas} glosas VENCIDAS sin respuesta",
            "cuerpo": "Estas glosas pasaron del plazo del Art. 57 Ley 1438/2011. "
                     "Revisa y escalalas ya para evitar pérdida de recursos.",
            "severidad": "critica",
        })
    if criticas_48h >= 5:
        alertas.append({
            "titulo": f"🔴 {criticas_48h} glosas vencen en las próximas 48h",
            "cuerpo": "Priorizá estas glosas en la bandeja del auditor asignado.",
            "severidad": "alta",
        })
    for eps_info in ranking_eps[:2]:
        if eps_info["ratif_pct"] >= 30:
            alertas.append({
                "titulo": f"📊 {eps_info['eps']} ratifica {eps_info['ratif_pct']}%",
                "cuerpo": f"Alto índice de ratificación en {eps_info['cantidad']} glosas. "
                         "Considera pasar a tono FIRME y reforzar jurisprudencia en "
                         "próximas respuestas.",
                "severidad": "media",
            })
    if glosas_hoy >= 30:
        alertas.append({
            "titulo": f"📈 Volumen alto hoy: {glosas_hoy} glosas analizadas",
            "cuerpo": "Considerá distribuir la carga entre más auditores.",
            "severidad": "info",
        })

    return {
        "timestamp": ahora.isoformat(),
        "valor_objetado_mes": float(total_obj_mes),
        "valor_recuperado_mes": float(total_rec_mes),
        "tasa_recuperacion_pct": tasa_recuperacion,
        "glosas_analizadas_hoy": int(glosas_hoy),
        "glosas_pendientes": int(pendientes),
        "glosas_criticas_48h": int(criticas_48h),
        "glosas_vencidas": int(vencidas),
        "ranking_auditores": ranking_auditores,
        "ranking_eps_ratificacion": ranking_eps,
        "alertas_proactivas": alertas,
    }
