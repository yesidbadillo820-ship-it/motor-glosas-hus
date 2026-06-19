"""Progreso en vivo del análisis de glosas via SSE.

El endpoint `POST /analizar` puede tardar 3-20s (PDFs + LLM + validación).
Sin progreso real, el frontend muestra una animación CSS estática del
pipeline (lo que el usuario llama "PIPELINE EN CURSO" sin saber qué pasa).

Este módulo expone:
  - `publicar(trace_id, etapa, datos)`: el endpoint llama esto en cada
    paso clave; si nadie escucha, el evento se descarta silenciosamente.
  - `obtener_cola(trace_id)`: el endpoint SSE crea/recupera la cola.
  - `cerrar_cola(trace_id)`: limpia al desconectar.

Diseñado intencionalmente simple — in-memory, sin Redis. Para una sola
instancia de Fly basta. Si escalamos a >1 instancia hay que migrar a
Redis pub/sub.
"""

from __future__ import annotations

import asyncio

# Mapeo trace_id → cola de eventos. Cada análisis tiene su propio trace_id
# generado por el frontend (uuid4) que va en (a) la conexión SSE abierta
# antes del POST, y (b) el form field 'trace_id' del POST /analizar.
_COLAS: dict[str, asyncio.Queue] = {}
_MAX_COLA = 50


def obtener_cola(trace_id: str) -> asyncio.Queue:
    """Devuelve la cola del trace_id, creándola si no existe."""
    cola = _COLAS.get(trace_id)
    if cola is None:
        cola = asyncio.Queue(maxsize=_MAX_COLA)
        _COLAS[trace_id] = cola
    return cola


def cerrar_cola(trace_id: str) -> None:
    """Elimina la cola asociada — llamar al cerrar el stream SSE."""
    _COLAS.pop(trace_id, None)


def publicar(trace_id: str, etapa: str, datos: dict | None = None) -> None:
    """Publica un evento de progreso en la cola de un trace_id.

    Si no hay cola (el frontend no abrió SSE), el evento se descarta
    silenciosamente — el análisis sigue su curso normal sin emitir.

    Args:
      trace_id: identificador único del análisis. Si está vacío, no-op.
      etapa: nombre corto del paso (ej. 'pdfs_extraidos', 'ia_iniciada')
      datos: payload arbitrario serializable a JSON (latencia, modelo, etc.)
    """
    if not trace_id:
        return
    cola = _COLAS.get(trace_id)
    if cola is None or cola.full():
        return
    try:
        cola.put_nowait({"etapa": etapa, "datos": datos or {}})
    except asyncio.QueueFull:
        pass
