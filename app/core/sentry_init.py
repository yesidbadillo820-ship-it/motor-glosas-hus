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


def _limpiar_dsn(raw: str) -> str:
    """Limpia artefactos comunes al pegar DSN (prefijo dsn=, comillas, espacios).

    Ejemplos de entrada → salida:
      'dsn="https://abc@o123.ingest.sentry.io/456"' → 'https://abc@o123.ingest.sentry.io/456'
      '"https://abc@..."' → 'https://abc@...'
      'dsn=https://abc@...' → 'https://abc@...'
      '  https://abc@... \n' → 'https://abc@...'
    """
    if not raw:
        return ""
    s = raw.strip()
    # Quitar prefijo dsn= o DSN=
    if s.lower().startswith("dsn="):
        s = s[4:].strip()
    # Quitar comillas simples o dobles que envuelvan el valor
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    # Quitar coma o punto y coma al final (si copiaron con la línea completa)
    s = s.rstrip(",;")
    return s.strip()


def _dsn_es_valido(dsn: str) -> tuple[bool, str]:
    """Valida rápido que el DSN tenga la forma esperada por Sentry.

    Formato correcto: https://KEY@o123456.ingest.sentry.io/PROJECT
    Retorna (valido, mensaje_error).
    """
    if not dsn:
        return False, "DSN vacío"
    if not (dsn.startswith("http://") or dsn.startswith("https://")):
        return False, (
            "DSN no inicia con http:// o https://. "
            "Copia el DSN completo desde sentry.io, debe verse como: "
            "https://abc123@o789.ingest.sentry.io/12345"
        )
    if "@" not in dsn or "ingest" not in dsn:
        return False, (
            "DSN con formato inválido. Copia el DSN completo desde "
            "sentry.io/settings → Client Keys (DSN)."
        )
    return True, ""


def init_sentry() -> bool:
    """Inicializa Sentry si hay DSN configurado.

    Returns:
        True si Sentry quedó activo, False si no se configuró o falló.

    CRÍTICO: cualquier fallo aquí NUNCA debe tumbar la aplicación.
    El error se loggea y se retorna False.
    """
    dsn_raw = os.getenv("SENTRY_DSN", "")
    dsn = _limpiar_dsn(dsn_raw)
    if dsn != dsn_raw.strip() and dsn_raw.strip():
        logger.warning(
            "SENTRY_DSN tenía artefactos (prefijo o comillas). Se limpió automáticamente."
        )
    if not dsn:
        logger.info("Sentry no configurado (sin SENTRY_DSN). Saltando inicialización.")
        return False

    # Validación del DSN antes de llamar init — evita BadDsn exception
    valido, err_msg = _dsn_es_valido(dsn)
    if not valido:
        logger.warning(f"SENTRY_DSN inválido ({err_msg}). Sentry desactivado. Valor actual: '{dsn[:30]}...'")
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

    # Endpoints ruidosos que NO queremos en performance traces — los
    # consume el load balancer y monitoring cada 30s. Si los muestreamos
    # al 10%, en 1 mes son ~8K eventos solo de health-checks que se
    # comen el quota free (5K/mes).
    _ENDPOINTS_RUIDOSOS = {
        "/health",
        "/sistema/version",
        "/sistema/ia-presence",
        "/notificaciones/badge",
        "/analytics/",
        "/glosas/alertas",
        "/metrics",
        "/favicon.ico",
    }

    def traces_sampler(sampling_context: dict) -> float:
        """Decide qué tracear. Excluye endpoints ruidosos al 100% y
        respeta el sample_rate base para el resto."""
        request = sampling_context.get("asgi_scope") or {}
        path = request.get("path") or ""
        if any(path == p or path.startswith(p + "?") for p in _ENDPOINTS_RUIDOSOS):
            return 0.0  # nunca tracear
        # WordPress probe spam (wp-admin/install.php, etc) tampoco vale la pena
        if path.startswith("/wp-") or path.startswith("/.env"):
            return 0.0
        return traces_sample_rate

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

    # Blindaje: cualquier error en init NO debe tumbar la app
    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            # traces_sampler tiene PREFERENCIA sobre traces_sample_rate
            # cuando ambos están — nos permite excluir endpoints ruidosos.
            traces_sampler=traces_sampler,
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
    except Exception as e:
        logger.error(
            f"Error inicializando Sentry (la app sigue funcionando sin tracking): {e}"
        )
        return False
    logger.info(
        f"Sentry activado | env={environment} | traces={traces_sample_rate} "
        f"| release={release or 'unspecified'}"
    )
    return True
