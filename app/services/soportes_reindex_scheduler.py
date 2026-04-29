"""Scheduler diario de reindexación del share de soportes.

Ejecuta `SoportesIndexer.rebuild()` cada día a las 2:00 AM. Hora elegida:
ventana de tráfico mínimo del HUS, antes del scheduler de mantenimiento
de las 3 AM. Así el primer gestor del día (~7 AM) encuentra el índice
caliente y no paga el costo del walk sobre CIFS.

Patrón idéntico a mantenimiento_scheduler: loop asyncio cancelado
limpiamente en shutdown del lifespan de FastAPI.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.core.logging_utils import logger

_HORA_OBJETIVO = 2  # 2:00 AM (antes del mantenimiento)

_task: Optional[asyncio.Task] = None


def _segundos_hasta_proxima_ejecucion() -> float:
    ahora = datetime.now()
    objetivo = ahora.replace(hour=_HORA_OBJETIVO, minute=0, second=0, microsecond=0)
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    return (objetivo - ahora).total_seconds()


async def _ejecutar_safe() -> None:
    try:
        from app.services.soportes_autodiscovery_service import get_indexer
        stats = get_indexer().rebuild()
        logger.info(
            f"[SOPORTES-REINDEX] OK: {stats['archivos_indexados']} archivos / "
            f"{stats['facturas_indexadas']} facturas"
        )
        if stats.get("ultimo_error"):
            logger.error(f"[SOPORTES-REINDEX] error: {stats['ultimo_error']}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[SOPORTES-REINDEX] falló ejecución: {e}")


async def _loop() -> None:
    # Build inicial al arrancar — así no hay que esperar a las 2 AM
    # del día siguiente. Si el mount aún no está listo, el indexador
    # registra `ultimo_error` y el healthz lo refleja.
    await _ejecutar_safe()
    while True:
        try:
            espera_s = _segundos_hasta_proxima_ejecucion()
            logger.info(f"[SOPORTES-REINDEX] Próxima ejecución en {espera_s/3600:.1f}h")
            await asyncio.sleep(espera_s)
            await _ejecutar_safe()
        except asyncio.CancelledError:
            logger.info("[SOPORTES-REINDEX] Scheduler cancelado (shutdown)")
            break
        except Exception as e:  # noqa: BLE001
            logger.error(f"[SOPORTES-REINDEX] error en loop: {e}. Reintento en 6h.")
            await asyncio.sleep(6 * 3600)


def iniciar_scheduler() -> None:
    """Inicia el loop. Idempotente.

    Optimización memoria (free tier): si la raíz de soportes NO existe,
    NO arrancamos el scheduler — sería un task de asyncio en background
    que solo loguea errores y consume RAM. Cuando Infra HUS conecte
    el mount o el jump-box agent empuje el primer batch, el endpoint
    /soportes-auto/reindex sí queda disponible para forzar manualmente.
    """
    global _task
    if _task is not None and not _task.done():
        logger.info("[SOPORTES-REINDEX] Scheduler ya estaba activo")
        return
    # Evitar arrancar el scheduler si no hay raíz accesible.
    try:
        from pathlib import Path
        import os as _os
        raiz = Path(_os.getenv("SOPORTES_ROOT", "/mnt/radicacion_2026"))
        if not raiz.exists():
            logger.info(
                f"[SOPORTES-REINDEX] Scheduler NO iniciado — raíz no existe: {raiz} "
                "(reactivá montando el share o configurando jump-box agent)"
            )
            return
    except Exception:
        pass  # si el check falla, seguimos como antes
    try:
        loop = asyncio.get_event_loop()
        _task = loop.create_task(_loop())
        logger.info("[SOPORTES-REINDEX] Scheduler iniciado (2 AM diario + build inicial)")
    except RuntimeError:
        logger.warning("[SOPORTES-REINDEX] No hay event loop, scheduler no iniciado")


def detener_scheduler() -> None:
    """Cancela el task si existe. Idempotente."""
    global _task
    if _task is None:
        return
    if not _task.done():
        _task.cancel()
    _task = None
    logger.info("[SOPORTES-REINDEX] Scheduler detenido")
