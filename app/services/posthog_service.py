"""PostHog (product analytics) — tracking server-side de eventos clave.

Para qué sirve en HUS:
  • Ver qué gestores son power-users vs los que apenas tocan la app
    (revela quién necesita capacitación, qué features se usan poco).
  • Medir embudo "Excel importado → IA respondió → Gestor revisa →
    Gestor radica" — saber dónde se cae la conversión.
  • Latencia real percibida (no solo la del backend) — el dashboard
    de PostHog te da p95/p99 sin escribirlo.
  • Feature flags si en algún sprint queremos probar A/B (ej. "nuevo
    diseño de dictamen para 30% de gestores").

Filosofía:
  • NUNCA mandar datos clínicos del paciente. Solo IDs y métricas.
  • Falla en silencio: si PostHog está down, el flujo de la app no se
    bloquea. Tracking es "best effort".
  • Si POSTHOG_API_KEY no está configurada, todo el módulo es no-op.

Setup:
  fly secrets set POSTHOG_API_KEY=phc_xxx -a motor-glosas-hus
  fly secrets set POSTHOG_HOST=https://us.posthog.com  # o eu.posthog.com
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("motor_glosas")


_cliente_posthog = None  # type: ignore[var-annotated]
_inicializado = False


def init_posthog() -> bool:
    """Inicializa el cliente PostHog si hay API key.

    Llamar 1 sola vez al startup. Returns True si quedó activo.
    Falla silenciosamente si la key no está o si la lib no se importa.
    """
    global _cliente_posthog, _inicializado
    if _inicializado:
        return _cliente_posthog is not None

    api_key = os.getenv("POSTHOG_API_KEY", "").strip()
    if not api_key:
        logger.info(
            "PostHog no configurado (sin POSTHOG_API_KEY). Tracking server-side desactivado."
        )
        _inicializado = True
        return False

    host = os.getenv("POSTHOG_HOST", "https://us.posthog.com").strip()

    try:
        from posthog import Posthog
    except ImportError:
        logger.warning("posthog no instalado. pip install posthog")
        _inicializado = True
        return False

    try:
        _cliente_posthog = Posthog(
            project_api_key=api_key,
            host=host,
            # disabled=False — explícito para que se vea
            sync_mode=False,  # async; no bloquea el request
            # max_queue_size=10000 default es ok
            # flush_at=20 default es ok
            # flush_interval=5 segundos default
        )
        logger.info(f"PostHog activado | host={host} | key={api_key[:8]}...")
    except Exception as e:
        logger.error(f"Error inicializando PostHog (la app sigue): {e}")
        _cliente_posthog = None

    _inicializado = True
    return _cliente_posthog is not None


def capture(
    event: str,
    distinct_id: str,
    properties: Optional[dict] = None,
) -> None:
    """Captura un evento server-side. Falla silencioso si PostHog
    no está activo o si hay error de red.

    Args:
      event: nombre del evento (snake_case). Ej: "glosa_analizada".
      distinct_id: id único del usuario (puede ser user_id, email, etc).
        Si no hay usuario, usar "anonimo".
      properties: dict opcional con metadata (NO mandar PHI del paciente).

    NOTA crítica: filtrar campos sensibles antes de pasarlos aquí.
      Permitido: gestor_id, eps, codigo_glosa, modelo_ia, latencia,
        estado, tipo_glosa, valor_objetado (agregado, no individual).
      Prohibido: nombre_paciente, documento_paciente, historia_clinica,
        cualquier texto libre que pueda contener datos del paciente.
    """
    if _cliente_posthog is None:
        return
    try:
        # Defensa: nunca aceptar campos que parezcan PHI por nombre
        props_filtradas = {}
        if properties:
            for k, v in properties.items():
                k_low = k.lower()
                if any(p in k_low for p in (
                    "paciente", "patient", "documento", "cedula",
                    "historia_clinica", "diagnostico_texto",
                )):
                    continue  # skip
                props_filtradas[k] = v
        _cliente_posthog.capture(
            distinct_id=str(distinct_id) if distinct_id else "anonimo",
            event=event,
            properties=props_filtradas,
        )
    except Exception as e:
        # No queremos que un fallo de tracking tumbe el flujo principal.
        logger.debug(f"[POSTHOG] capture {event!r} falló: {e}")


def identify(distinct_id: str, properties: Optional[dict] = None) -> None:
    """Asocia metadata a un usuario (rol, eps_principal, fecha_creacion).
    No envía PHI."""
    if _cliente_posthog is None:
        return
    try:
        _cliente_posthog.identify(
            distinct_id=str(distinct_id),
            properties=properties or {},
        )
    except Exception as e:
        logger.debug(f"[POSTHOG] identify falló: {e}")


def disponible() -> bool:
    """Devuelve True si PostHog está activo y aceptando eventos."""
    return _cliente_posthog is not None


def shutdown() -> None:
    """Flush + cerrar antes de apagar el server. Llamar en lifespan
    shutdown para evitar perder eventos en cola."""
    if _cliente_posthog is None:
        return
    try:
        _cliente_posthog.flush()
        _cliente_posthog.shutdown()
    except Exception as e:
        logger.debug(f"[POSTHOG] shutdown falló: {e}")
