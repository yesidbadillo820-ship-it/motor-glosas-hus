"""Scheduler diario del resumen Telegram (8:00 AM local).

Cada mañana le manda a cada gestor vinculado un push con sus glosas
ROJAS y NEGRAS pendientes. Pensado para que el gestor abra Telegram al
levantarse y vea en un vistazo qué tiene que atacar hoy.

Patrón idéntico a `mantenimiento_scheduler` — loop asyncio que se
cancela limpiamente en shutdown del lifespan FastAPI.

No-op si `TELEGRAM_BOT_TOKEN` no está configurado.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.core.logging_utils import logger
from app.services import telegram_service

_HORA_OBJETIVO = 8  # 8:00 AM local — antes que arranquen la jornada
_MINUTO_OBJETIVO = 0

_task: Optional[asyncio.Task] = None


def _segundos_hasta_proxima_ejecucion() -> float:
    """Segundos hasta las próximas 8:00 AM (hora del servidor)."""
    ahora = datetime.now()
    objetivo = ahora.replace(
        hour=_HORA_OBJETIVO, minute=_MINUTO_OBJETIVO, second=0, microsecond=0,
    )
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    return (objetivo - ahora).total_seconds()


async def _ejecutar_safe() -> None:
    """Abre DB, llama al resumen, captura cualquier error."""
    if not telegram_service.disponible():
        logger.info("[TELEGRAM-RESUMEN] saltado: TELEGRAM_BOT_TOKEN no configurado")
        return
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            stats = await telegram_service.enviar_resumen_diario(db)
            logger.info(f"[TELEGRAM-RESUMEN] OK: {stats}")
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.error(f"[TELEGRAM-RESUMEN] falló ejecución: {e}")


async def _loop_resumen() -> None:
    while True:
        try:
            espera_s = _segundos_hasta_proxima_ejecucion()
            horas = espera_s / 3600
            logger.info(f"[TELEGRAM-RESUMEN] Próxima ejecución en {horas:.1f}h")
            await asyncio.sleep(espera_s)
            await _ejecutar_safe()
        except asyncio.CancelledError:
            logger.info("[TELEGRAM-RESUMEN] Scheduler cancelado (shutdown)")
            break
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"[TELEGRAM-RESUMEN] Error en loop: {e}. Reintentando en 6h."
            )
            await asyncio.sleep(6 * 3600)


def iniciar_scheduler() -> None:
    """Idempotente. Si TELEGRAM_BOT_TOKEN no está, igual arranca el
    loop (que loguea 'saltado' cada día) — útil para detectar setup
    incorrecto en logs sin que cause errores."""
    global _task
    if _task is not None and not _task.done():
        logger.info("[TELEGRAM-RESUMEN] Scheduler ya estaba activo, no re-inicio")
        return
    try:
        loop = asyncio.get_event_loop()
        _task = loop.create_task(_loop_resumen())
        logger.info("[TELEGRAM-RESUMEN] Scheduler iniciado (8 AM diario)")
    except RuntimeError:
        logger.warning("[TELEGRAM-RESUMEN] No hay event loop, scheduler no iniciado")


def detener_scheduler() -> None:
    global _task
    if _task is None:
        return
    if not _task.done():
        _task.cancel()
    _task = None
    logger.info("[TELEGRAM-RESUMEN] Scheduler detenido")
