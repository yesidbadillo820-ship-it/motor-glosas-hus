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

# 11-09-2026 — POR QUÉ EL ARRANQUE YA NO RECORRE SIEMPRE.
#
# El motor del hospital se autodespliega: baja la rama cada 5 minutos y, si
# hay commit nuevo, se reinicia. O sea que hay reinicios A CUALQUIER HORA del
# día laboral, no solo de madrugada.
#
# Y al arrancar se recorría el servidor de archivos ENTERO, sin preguntar si
# hacía falta. Con 101.991 facturas y 426.405 archivos al otro lado de la red
# (`\\Prime\radicacion_2026`), eso son cientos de miles de viajes por red
# que se llevan minutos, machacan el servidor de archivos y le roban turno al
# motor mientras el auditor trabaja. El caso de hoy: se fusionó un cambio a
# las 8:16 a.m., el motor se reinició, y a las 8:35 seguía recorriendo.
#
# El recorrido diario de las 2 AM ya deja el índice al día. Repetirlo porque
# hubo un despliegue no agrega NADA: son los mismos archivos. Así que al
# arrancar solo se recorre si de verdad falta —índice vacío, o tan viejo que
# se perdió el turno de las 2 AM porque el motor estaba apagado—.
#
# Lo que NO cambia: el botón «Reindexar ahora» sigue recorriendo cuando el
# auditor lo pide, y el turno de las 2 AM sigue igual.
_HORAS_PARA_NO_REPETIR = 20.0

_task: Optional[asyncio.Task] = None


def _segundos_hasta_proxima_ejecucion() -> float:
    ahora = datetime.now()
    objetivo = ahora.replace(hour=_HORA_OBJETIVO, minute=0, second=0, microsecond=0)
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    return (objetivo - ahora).total_seconds()


async def _ejecutar_safe(*, solo_si_hace_falta: bool = False) -> None:
    try:
        from app.services.soportes_autodiscovery_service import get_indexer

        if solo_si_hace_falta:
            edad_s = get_indexer().construido_hace()
            if edad_s is not None and edad_s < _HORAS_PARA_NO_REPETIR * 3600:
                logger.info(
                    f"[SOPORTES-REINDEX] El índice se recorrió hace {edad_s / 3600:.1f}h; "
                    "no se vuelve a recorrer el servidor por un reinicio. "
                    "El turno de las 2 AM sigue en pie."
                )
                return

        # Ronda 30: rebuild() recorre el share CIFS completo (IO/CPU-bound).
        # Corría síncrono dentro de esta corrutina y bloqueaba el event loop
        # —congelando TODO el sitio— durante el build inicial al arranque y
        # cada reindex. Se ejecuta en un thread aparte.
        stats = await asyncio.to_thread(get_indexer().rebuild)
        logger.info(
            f"[SOPORTES-REINDEX] OK: {stats['archivos_indexados']} archivos / "
            f"{stats['facturas_indexadas']} facturas"
        )
        if stats.get("ultimo_error"):
            logger.error(f"[SOPORTES-REINDEX] error: {stats['ultimo_error']}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[SOPORTES-REINDEX] falló ejecución: {e}")


async def _loop() -> None:
    # Build inicial al arrancar SOLO SI HACE FALTA — así no hay que esperar a
    # las 2 AM del día siguiente cuando el motor estuvo apagado, pero tampoco
    # se recorre el servidor entero cada vez que un despliegue lo reinicia.
    # Si el mount aún no está listo, el indexador registra `ultimo_error` y el
    # healthz lo refleja.
    await _ejecutar_safe(solo_si_hace_falta=True)
    while True:
        try:
            espera_s = _segundos_hasta_proxima_ejecucion()
            logger.info(f"[SOPORTES-REINDEX] Próxima ejecución en {espera_s / 3600:.1f}h")
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
    # Evitar arrancar el scheduler si la raíz claramente no aplica.
    # Con la nueva resolución de raíz (autodiscovery_service.py) el
    # default es /tmp/motor-soportes que SIEMPRE existe (se crea on
    # init), así que normalmente el scheduler arranca. Solo lo
    # apagamos si el operador setea SOPORTES_ROOT explícitamente a un
    # path que no existe (ej. mount CIFS no montado todavía).
    try:
        from pathlib import Path
        import os as _os

        raiz_explicita = _os.getenv("SOPORTES_ROOT")
        if raiz_explicita and not Path(raiz_explicita).exists():
            logger.info(
                f"[SOPORTES-REINDEX] Scheduler NO iniciado — SOPORTES_ROOT "
                f"explícito no existe: {raiz_explicita}. Configurá Plan A "
                f"(mount CIFS) o quitá la variable para usar Plan B "
                f"(jump-box → /tmp/motor-soportes)."
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
