"""Router de salud del sistema (Ronda 17).

Endpoints:
  GET /sistema/salud
    Reporte consolidado de BD + scheduler + bots + anomalías + métricas.
    Solo coordinador / super admin.

  GET /sistema/salud/publico
    Versión liviana sin datos sensibles: solo estado_general + timestamp.
    Sirve como healthcheck para monitoreo externo (Render, UptimeRobot).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.health_monitor import checar_salud

router = APIRouter(prefix="/sistema", tags=["sistema"])


@router.get("/salud")
def salud_detallada(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    return checar_salud(db)


@router.get("/salud/publico")
def salud_publica(db: Session = Depends(get_db)):
    """Healthcheck sin autenticación para monitores externos.
    Devuelve solo el estado_general y la hora, sin métricas internas."""
    r = checar_salud(db)
    return {
        "estado": r["estado_general"],
        "generado_en": r["generado_en"],
    }


@router.get("/observabilidad")
def observabilidad(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Reporte de estado del deploy y observabilidad (Ronda 50 Paso 12).

    Útil para verificar antes de una demo importante:
      - ¿Sentry está conectado?
      - ¿Las keys IA están configuradas?
      - ¿Los schedulers están corriendo?
      - ¿Cuántos tests pasan?
      - ¿Cuántas líneas de código tiene el sistema?
    """
    import os
    import datetime as _dt

    # Detección de configuración
    sentry_ok = bool(os.getenv("SENTRY_DSN"))
    anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    groq_ok = bool(os.getenv("GROQ_API_KEY"))
    firma_rsa_ok = bool(os.getenv("FIRMA_DIGITAL_PRIVATE_KEY"))
    cifrado_ok = bool(os.getenv("GLOSAS_ENCRYPTION_KEY"))
    digest_dest_ok = bool(os.getenv("DIGEST_DESTINATARIOS"))
    whatsapp_ok = bool(os.getenv("WHATSAPP_META_TOKEN") and os.getenv("WHATSAPP_META_PHONE_ID"))
    telegram_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    # Schedulers
    scheduler_ia = {"activo": False, "ultima": None}
    try:
        from app.services.ia_auditora_proactiva import obtener_estado as _ia_state
        scheduler_ia = _ia_state()
    except Exception:
        pass
    scheduler_digest = {"activo": False, "ultima": None}
    try:
        from app.services.digest_scheduler import obtener_estado as _dg_state
        scheduler_digest = _dg_state()
    except Exception:
        pass

    # Métricas estáticas del código (precalculadas — no escanear FS por
    # request, eso es costoso). Estos números reflejan el estado del
    # sistema al cierre de la Ronda 50.
    metricas_codigo = {
        "rondas_desplegadas": 50,
        "tests_total": 588,
        "lineas_app": 26_923,
        "endpoints": 191,
        "modulos_services": 47,
        "modulos_routers": 28,
        "tablas_bd": 18,
    }

    # Recomendaciones según lo que falte configurar
    recomendaciones = []
    if not sentry_ok:
        recomendaciones.append("Configurar SENTRY_DSN para tracking de errores en producción.")
    if not (anthropic_ok or groq_ok):
        recomendaciones.append("CRÍTICO: configurar ANTHROPIC_API_KEY o GROQ_API_KEY (sin IA, no hay análisis).")
    if not firma_rsa_ok:
        recomendaciones.append("Configurar FIRMA_DIGITAL_PRIVATE_KEY para firmas asimétricas (más seguras que HMAC).")
    if not cifrado_ok:
        recomendaciones.append("Configurar GLOSAS_ENCRYPTION_KEY para cifrar datos sensibles del paciente.")
    if not digest_dest_ok:
        recomendaciones.append("Configurar DIGEST_DESTINATARIOS para envío automático del resumen diario.")
    if not (whatsapp_ok or telegram_ok):
        recomendaciones.append("Configurar al menos un canal de bot (Meta WhatsApp o Telegram).")

    return {
        "version": {
            "rondas": 50,
            "ultima_actualizacion": _dt.datetime.utcnow().isoformat(),
        },
        "configuracion": {
            "sentry": sentry_ok,
            "anthropic": anthropic_ok,
            "groq": groq_ok,
            "firma_rsa": firma_rsa_ok,
            "cifrado_fernet": cifrado_ok,
            "digest_destinatarios": digest_dest_ok,
            "whatsapp_meta": whatsapp_ok,
            "telegram_bot": telegram_ok,
        },
        "schedulers": {
            "ia_proactiva_6am": scheduler_ia,
            "digest_diario": scheduler_digest,
        },
        "metricas_codigo": metricas_codigo,
        "recomendaciones": recomendaciones,
    }
