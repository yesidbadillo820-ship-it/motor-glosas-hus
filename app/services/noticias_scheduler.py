"""Scheduler de actualización de noticias del sector salud Colombia.

Corre cada 4 horas. Ventana suficiente para mantener el ticker fresco
sin saturar las fuentes (que algunas son sensibles a polling agresivo).

Patrón idéntico a mantenimiento_scheduler: loop asyncio cancelable
limpiamente en shutdown del lifespan de FastAPI.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.core.logging_utils import logger

_INTERVALO_HORAS = 4
_task: Optional[asyncio.Task] = None


async def _loop_noticias() -> None:
    """Loop infinito: ejecuta primer fetch al arranque, luego cada 4h."""
    # Build inicial al startup (con delay corto para no chocar con
    # el resto de schedulers iniciando)
    try:
        await asyncio.sleep(60)
        await _ejecutar_safe()
    except asyncio.CancelledError:
        logger.info("[NOTICIAS-SCHED] Scheduler cancelado (shutdown)")
        return
    except Exception as e:
        logger.error(f"[NOTICIAS-SCHED] Build inicial falló: {e}")

    while True:
        try:
            espera_s = _INTERVALO_HORAS * 3600
            logger.info(f"[NOTICIAS-SCHED] Próxima ejecución en {_INTERVALO_HORAS}h")
            await asyncio.sleep(espera_s)
            await _ejecutar_safe()
        except asyncio.CancelledError:
            logger.info("[NOTICIAS-SCHED] Scheduler cancelado (shutdown)")
            break
        except Exception as e:
            logger.error(f"[NOTICIAS-SCHED] Error en loop: {e}. Reintentando en 1h.")
            await asyncio.sleep(3600)


async def _ejecutar_safe() -> None:
    """Wrapper resiliente — captura cualquier error sin matar el loop."""
    try:
        from app.services.noticias_salud_co import actualizar_noticias
        stats = await actualizar_noticias()
        logger.info(f"[NOTICIAS-SCHED] OK: {stats}")
    except Exception as e:
        logger.error(f"[NOTICIAS-SCHED] Ejecución falló: {e}")


def iniciar_scheduler() -> None:
    """Inicia el loop. Idempotente."""
    global _task
    if _task is not None and not _task.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _task = loop.create_task(_loop_noticias())
        logger.info(f"[NOTICIAS-SCHED] Scheduler iniciado (cada {_INTERVALO_HORAS}h)")
    except RuntimeError:
        logger.warning("[NOTICIAS-SCHED] No hay event loop, scheduler no iniciado")


def detener_scheduler() -> None:
    """Cancela el task si existe. Idempotente."""
    global _task
    if _task is None:
        return
    if not _task.done():
        _task.cancel()
    _task = None
    logger.info("[NOTICIAS-SCHED] Scheduler detenido")
