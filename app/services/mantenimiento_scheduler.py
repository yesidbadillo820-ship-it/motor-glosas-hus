"""Scheduler diario de mantenimiento (R57 P2).

Ejecuta `ejecutar_mantenimiento_completo()` cada día a las 3:00 AM.
Hora elegida: ventana de tráfico mínimo del HUS (gestores duermen).

Patrón idéntico a ia_auditora_proactiva: loop asyncio que se cancela
limpiamente en shutdown del lifespan de FastAPI.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.core.logging_utils import logger

_HORA_OBJETIVO = 3  # 3:00 AM

_task: Optional[asyncio.Task] = None


def _segundos_hasta_proxima_ejecucion() -> float:
    """Segundos hasta las próximas 3:00 AM (hora local del servidor)."""
    ahora = datetime.now()
    objetivo = ahora.replace(hour=_HORA_OBJETIVO, minute=0, second=0, microsecond=0)
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    return (objetivo - ahora).total_seconds()


async def _loop_mantenimiento() -> None:
    """Loop infinito: espera hasta las 3 AM, ejecuta, repite. Resistente
    a excepciones — si falla una iteración, reintenta en 6h."""
    while True:
        try:
            espera_s = _segundos_hasta_proxima_ejecucion()
            horas = espera_s / 3600
            logger.info(f"[MANTENIMIENTO] Próxima ejecución en {horas:.1f}h")
            await asyncio.sleep(espera_s)
            await _ejecutar_safe()
        except asyncio.CancelledError:
            logger.info("[MANTENIMIENTO] Scheduler cancelado (shutdown)")
            break
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"[MANTENIMIENTO] Error en loop: {e}. Reintentando en 6h."
            )
            await asyncio.sleep(6 * 3600)


async def _ejecutar_safe() -> None:
    """Wrapper que abre/cierra DB y captura todo error."""
    try:
        from app.database import SessionLocal
        from app.services.mantenimiento import ejecutar_mantenimiento_completo

        db = SessionLocal()
        try:
            stats = ejecutar_mantenimiento_completo(db)
            logger.info(f"[MANTENIMIENTO] OK: {stats}")
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.error(f"[MANTENIMIENTO] falló ejecución: {e}")


def iniciar_scheduler() -> None:
    """Inicia el loop. Idempotente: si ya está corriendo no hace nada."""
    global _task
    if _task is not None and not _task.done():
        logger.info("[MANTENIMIENTO] Scheduler ya estaba activo, no re-inicio")
        return
    try:
        loop = asyncio.get_event_loop()
        _task = loop.create_task(_loop_mantenimiento())
        logger.info("[MANTENIMIENTO] Scheduler iniciado (3 AM diario)")
    except RuntimeError:
        # No hay event loop activo — caso de tests o invocación fuera de FastAPI
        logger.warning("[MANTENIMIENTO] No hay event loop, scheduler no iniciado")


def detener_scheduler() -> None:
    """Cancela el task si existe. Idempotente."""
    global _task
    if _task is None:
        return
    if not _task.done():
        _task.cancel()
    _task = None
    logger.info("[MANTENIMIENTO] Scheduler detenido")
