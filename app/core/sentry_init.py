"""
sentry_init.py — Inicialización de Sentry error tracking.
==========================================================
Solo activa Sentry si la variable SENTRY_DSN está definida. En dev local
(sin la variable) no hace nada, evitando ruido.

Uso:
    from app.core.sentry_init import init_sentry
    init_sentry()  # al arranque de la app

Variables de entorno:
    SENTRY_DSN              — DSN completo de Sentry (obligatorio para activar)
    SENTRY_ENVIRONMENT      — production | staging | development (default: production)
    SENTRY_TRACES_SAMPLE_RATE  — 0.0-1.0 para performance (default: 0.1 = 10%)
    SENTRY_RELEASE          — identificador de versión (default: commit SHA si existe)
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger("motor_glosas")


def init_sentry() -> bool:
    """Inicializa Sentry si hay DSN configurado.

    Returns:
        True si Sentry quedó activo, False si no se configuró.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("Sentry no configurado (sin SENTRY_DSN). Saltando inicialización.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning("sentry-sdk no está instalado. Corre: pip install sentry-sdk[fastapi]")
        return False

    environment = os.getenv("SENTRY_ENVIRONMENT", "production")
    try:
        traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    except ValueError:
        traces_sample_rate = 0.1
    release = os.getenv("SENTRY_RELEASE") or os.getenv("RENDER_GIT_COMMIT", "")[:12] or None

    # Configuración de logging integrado: captura WARN+ como breadcrumbs, ERROR+ como eventos
    logging_integration = LoggingIntegration(
        level=logging.INFO,      # nivel mínimo para breadcrumbs
        event_level=logging.ERROR,  # nivel mínimo para crear event en Sentry
    )

    # Hook para filtrar información sensible antes de enviar
    def before_send(event, hint):
        # Redactar headers de autorización / cookies
        request = event.get("request") or {}
        headers = request.get("headers") or {}
        for sensitive in ("authorization", "cookie", "x-api-key", "x-auth-token"):
            if sensitive in headers:
                headers[sensitive] = "[REDACTED]"
            if sensitive.title() in headers:
                headers[sensitive.title()] = "[REDACTED]"
        # Redactar query string si contiene "password" o "token"
        qs = request.get("query_string") or ""
        if isinstance(qs, str) and ("password" in qs.lower() or "token" in qs.lower()):
            request["query_string"] = "[REDACTED]"
        # No enviar datos de POST form (pueden contener glosas con PHI)
        if "data" in request:
            request["data"] = "[REDACTED - contiene datos de glosa posiblemente con PHI]"
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=0.0,  # desactivado por defecto (overhead)
        send_default_pii=False,    # no enviar PII por defecto
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            logging_integration,
        ],
        before_send=before_send,
        # Ignorar errores esperados (401/403/404 no son bugs)
        ignore_errors=[
            "HTTPException",  # Excepciones 4xx intencionales
        ],
    )
    logger.info(
        f"Sentry activado | env={environment} | traces={traces_sample_rate} "
        f"| release={release or 'unspecified'}"
    )
    return True
