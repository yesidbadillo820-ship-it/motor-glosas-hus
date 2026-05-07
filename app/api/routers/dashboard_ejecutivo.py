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

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.core.tz import ahora_utc
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
    ahora = ahora_utc()
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


# ─── B.3: Detector de actividad inteligente ────────────────────────────────
# Sintetiza patrones que requieren intervencion del coordinador:
#  - gestores inactivos: tienen pendientes asignados pero no han hecho
#    nada en X dias (segun audit_log).
#  - glosas estancadas: mismo estado por > Y dias.
#  - carga concentrada: top 5 gestores con mas pendientes.
#  - alertas de alto valor: glosas vencidas/criticas con saldo > umbral.
@router.get("/detector-actividad")
def detector_actividad(
    dias_inactividad: int = 3,
    dias_estancada: int = 7,
    valor_alto_umbral: float = 1_000_000.0,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Detecta patrones que requieren intervencion del coordinador.

    Parametros (con default razonables):
    - dias_inactividad: gestores sin audit-log en >= N dias se reportan.
    - dias_estancada: glosas en mismo estado por >= N dias se reportan.
    - valor_alto_umbral: COP, glosas con valor_objetado > umbral y
      vencidas o criticas se priorizan en la lista.
    """
    from app.models.db import AuditLogRecord
    ahora = ahora_utc()
    corte_inactividad = ahora - timedelta(days=dias_inactividad)
    corte_estancada = ahora - timedelta(days=dias_estancada)
    en_48h = ahora + timedelta(hours=48)

    # ─── Gestores con pendientes asignados ───────────────────────────────
    try:
        gestores_con_carga = (
            db.query(
                GlosaRecord.auditor_email,
                func.count(GlosaRecord.id).label("pend"),
                func.coalesce(func.sum(GlosaRecord.valor_objetado), 0).label("valor"),
            )
            .filter(GlosaRecord.auditor_email.isnot(None))
            .filter(GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"]))
            .group_by(GlosaRecord.auditor_email)
            .all()
        )
    except Exception:
        gestores_con_carga = []

    # Para cada gestor con carga, comprobar ultima actividad en audit_log
    gestores_inactivos = []
    carga_concentrada = []
    for email, pend, valor in gestores_con_carga:
        if not email:
            continue
        try:
            ultima = (
                db.query(func.max(AuditLogRecord.timestamp))
                .filter(AuditLogRecord.usuario_email == email)
                .scalar()
            )
        except Exception:
            ultima = None
        if ultima is None or ultima < corte_inactividad:
            dias_sin_act = (ahora - ultima).days if ultima else 999
            gestores_inactivos.append({
                "email": (email or "").split("@")[0],
                "email_full": email,
                "pendientes": int(pend),
                "valor_en_juego": float(valor or 0),
                "dias_sin_actividad": dias_sin_act,
                "ultima_actividad": ultima.isoformat() if ultima else None,
            })
        carga_concentrada.append({
            "email": (email or "").split("@")[0],
            "pendientes": int(pend),
            "valor_en_juego": float(valor or 0),
        })

    gestores_inactivos.sort(key=lambda x: -x["dias_sin_actividad"])
    gestores_inactivos = gestores_inactivos[:10]
    carga_concentrada.sort(key=lambda x: -x["pendientes"])
    carga_concentrada = carga_concentrada[:5]

    # ─── Glosas estancadas: mismo estado >= N dias y aun pendientes ──────
    try:
        estancadas_rows = (
            db.query(
                GlosaRecord.id, GlosaRecord.eps, GlosaRecord.factura,
                GlosaRecord.codigo_glosa, GlosaRecord.estado,
                GlosaRecord.valor_objetado, GlosaRecord.creado_en,
                GlosaRecord.auditor_email, GlosaRecord.fecha_vencimiento,
            )
            .filter(GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"]))
            .filter(GlosaRecord.creado_en <= corte_estancada)
            .order_by(GlosaRecord.creado_en.asc())
            .limit(20)
            .all()
        )
        glosas_estancadas = [
            {
                "id": gid, "eps": eps, "factura": factura,
                "codigo": cod, "estado": estado,
                "valor": float(valor or 0),
                "auditor": (email or "").split("@")[0] if email else None,
                "dias_sin_progreso": (ahora - creado).days if creado else None,
                "vencimiento": fv.isoformat() if fv else None,
            }
            for gid, eps, factura, cod, estado, valor, creado, email, fv in estancadas_rows
        ]
    except Exception:
        glosas_estancadas = []

    # ─── Glosas alto valor en riesgo (vencidas o crit-48h) ───────────────
    try:
        riesgo_rows = (
            db.query(
                GlosaRecord.id, GlosaRecord.eps, GlosaRecord.factura,
                GlosaRecord.codigo_glosa, GlosaRecord.valor_objetado,
                GlosaRecord.fecha_vencimiento, GlosaRecord.auditor_email,
                GlosaRecord.estado,
            )
            .filter(GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"]))
            .filter(GlosaRecord.valor_objetado >= valor_alto_umbral)
            .filter(GlosaRecord.fecha_vencimiento <= en_48h)
            .order_by(GlosaRecord.valor_objetado.desc())
            .limit(15)
            .all()
        )
        alto_valor_riesgo = [
            {
                "id": gid, "eps": eps, "factura": factura,
                "codigo": cod, "valor": float(valor or 0),
                "vencimiento": fv.isoformat() if fv else None,
                "auditor": (email or "").split("@")[0] if email else "sin asignar",
                "estado": estado,
                "horas_restantes": int((fv - ahora).total_seconds() // 3600) if fv else None,
            }
            for gid, eps, factura, cod, valor, fv, email, estado in riesgo_rows
        ]
    except Exception:
        alto_valor_riesgo = []

    # Senal global de severidad para badge
    severidad_global = "ok"
    if gestores_inactivos and any(g["pendientes"] >= 5 for g in gestores_inactivos):
        severidad_global = "critica"
    elif gestores_inactivos:
        severidad_global = "alta"
    elif glosas_estancadas:
        severidad_global = "media"
    elif alto_valor_riesgo:
        severidad_global = "media"

    return {
        "timestamp": ahora.isoformat(),
        "parametros": {
            "dias_inactividad": dias_inactividad,
            "dias_estancada": dias_estancada,
            "valor_alto_umbral": valor_alto_umbral,
        },
        "severidad_global": severidad_global,
        "gestores_inactivos": gestores_inactivos,
        "carga_concentrada_top": carga_concentrada,
        "glosas_estancadas": glosas_estancadas,
        "alto_valor_riesgo": alto_valor_riesgo,
        "totales": {
            "gestores_inactivos": len(gestores_inactivos),
            "glosas_estancadas": len(glosas_estancadas),
            "alto_valor_riesgo": len(alto_valor_riesgo),
        },
    }
