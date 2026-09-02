"""Dónde se guarda el resultado de un análisis que corre en el fondo.

02-09-2026 — PRUEBA 2 (CL4506). El túnel corta toda respuesta a los 100 s y
el análisis de una glosa pesada tarda más. El motor terminaba el dictamen y lo
guardaba en el historial, pero la respuesta nunca llegaba al navegador: el
auditor veía «Error de conexión» y daba la prueba por caída. Para él, eso ES
una caída — con razón.

La solución no es acortar el trabajo ni mandarlo al Historial: es que ninguna
petición dure más que el túnel. El POST devuelve el trace_id de inmediato, el
análisis corre aparte, y la pantalla pregunta por el resultado con peticiones
cortas. Este módulo es la memoria entre las dos puntas.

Vive en memoria del proceso, como la cola de progreso: sobrevive lo que dura
el análisis, que es lo que hace falta. Si el motor se reinicia a mitad, el
resultado se pierde de aquí pero NO del historial, que sigue siendo la fuente.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

# 30 minutos alcanzan para que la pantalla lo recoja; un análisis nunca vive
# tanto. Y un tope de entradas para que un bot con miles de trace_id no coma
# memoria.
_TTL_SEGUNDOS = 30 * 60
_MAX_ENTRADAS = 500

_RESULTADOS: dict[str, dict[str, Any]] = {}
_CANDADO = threading.Lock()


def _purgar() -> None:
    """Saca lo vencido. Se llama con el candado tomado."""
    ahora = time.time()
    vencidos = [t for t, e in _RESULTADOS.items() if ahora - e["creado"] > _TTL_SEGUNDOS]
    for t in vencidos:
        _RESULTADOS.pop(t, None)
    if len(_RESULTADOS) > _MAX_ENTRADAS:
        # Los más viejos primero.
        for t, _ in sorted(_RESULTADOS.items(), key=lambda kv: kv[1]["creado"])[
            : len(_RESULTADOS) - _MAX_ENTRADAS
        ]:
            _RESULTADOS.pop(t, None)


def abrir(trace_id: str) -> None:
    """Registra que un análisis arrancó. Desde aquí «en_curso»."""
    with _CANDADO:
        _purgar()
        _RESULTADOS[trace_id] = {
            "estado": "en_curso",
            "creado": time.time(),
            "resultado": None,
            "glosa_id": None,
            "detail": None,
            "status": None,
        }


def cerrar_ok(trace_id: str, resultado: Any, glosa_id: Optional[int] = None) -> None:
    with _CANDADO:
        e = _RESULTADOS.get(trace_id)
        if e is None:
            e = {"creado": time.time()}
            _RESULTADOS[trace_id] = e
        e.update({"estado": "listo", "resultado": resultado, "glosa_id": glosa_id, "detail": None})


def cerrar_error(trace_id: str, detail: str, status: int = 500) -> None:
    with _CANDADO:
        e = _RESULTADOS.get(trace_id)
        if e is None:
            e = {"creado": time.time()}
            _RESULTADOS[trace_id] = e
        e.update({"estado": "error", "detail": (detail or "")[:500], "status": int(status)})


def consultar(trace_id: str) -> Optional[dict[str, Any]]:
    """Copia del estado, o None si nunca existió (o ya venció)."""
    with _CANDADO:
        _purgar()
        e = _RESULTADOS.get(trace_id)
        return dict(e) if e is not None else None


def _vaciar_para_pruebas() -> None:
    with _CANDADO:
        _RESULTADOS.clear()
