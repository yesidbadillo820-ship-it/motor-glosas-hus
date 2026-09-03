"""Dónde vive el estado de un LOTE de análisis masivo (endpoint /analizar/masivo/).

02-09-2026 (V2, Pilar 1). El auditor sube un CSV con muchas glosas y un ZIP con
sus PDF; el motor las procesa en el fondo, unas cuantas a la vez, y arma un solo
Excel con todos los dictámenes. Este módulo es la memoria del lote mientras
corre: cuántas van, cuántas salieron bien o mal, y el archivo consolidado listo
para descargar.

Igual que `resultados_analisis`, vive en memoria del proceso: sobrevive lo que
dura el lote. Cada glosa, además, se persiste en el historial por el camino de
siempre (`_analizar_impl`), que sigue siendo la fuente de verdad; si el motor se
reinicia a mitad, se pierde el consolidado de aquí pero no los dictámenes.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

# Un lote grande puede tardar; hora y media de vida alcanza para procesar y
# descargar. Y un tope de lotes vivos para no comer memoria.
_TTL_SEGUNDOS = 90 * 60
_MAX_LOTES = 50

_LOTES: dict[str, dict[str, Any]] = {}
_CANDADO = threading.Lock()


def _purgar() -> None:
    ahora = time.time()
    for j in [k for k, e in _LOTES.items() if ahora - e["creado"] > _TTL_SEGUNDOS]:
        _LOTES.pop(j, None)
    if len(_LOTES) > _MAX_LOTES:
        for j, _ in sorted(_LOTES.items(), key=lambda kv: kv[1]["creado"])[
            : len(_LOTES) - _MAX_LOTES
        ]:
            _LOTES.pop(j, None)


def abrir(job_id: str, total: int) -> None:
    with _CANDADO:
        _purgar()
        _LOTES[job_id] = {
            "estado": "en_curso",
            "creado": time.time(),
            "total": int(total),
            "hechas": 0,
            "ok": 0,
            "error": 0,
            "filas": [],  # resúmenes por glosa (para el Excel consolidado)
            "archivo": None,  # bytes del XLSX cuando termina
            "detail": None,
        }


def registrar_fila(job_id: str, fila: dict[str, Any], es_error: bool = False) -> None:
    """Guarda el resumen de una glosa ya procesada y avanza los contadores."""
    with _CANDADO:
        e = _LOTES.get(job_id)
        if e is None:
            return
        e["filas"].append(fila)
        e["hechas"] += 1
        e["error" if es_error else "ok"] += 1


def cerrar_ok(job_id: str, archivo_bytes: bytes) -> None:
    with _CANDADO:
        e = _LOTES.get(job_id)
        if e is None:
            return
        e["estado"] = "listo"
        e["archivo"] = archivo_bytes


def cerrar_error(job_id: str, detail: str) -> None:
    with _CANDADO:
        e = _LOTES.get(job_id)
        if e is None:
            return
        e["estado"] = "error"
        e["detail"] = (detail or "")[:500]


def consultar(job_id: str) -> Optional[dict[str, Any]]:
    """Estado del lote SIN el archivo ni el detalle de filas (para el progreso)."""
    with _CANDADO:
        _purgar()
        e = _LOTES.get(job_id)
        if e is None:
            return None
        return {
            "estado": e["estado"],
            "total": e["total"],
            "hechas": e["hechas"],
            "ok": e["ok"],
            "error": e["error"],
            "detail": e.get("detail"),
            "tiene_archivo": e.get("archivo") is not None,
        }


def filas(job_id: str) -> list[dict[str, Any]]:
    with _CANDADO:
        e = _LOTES.get(job_id)
        return list(e["filas"]) if e else []


def obtener_archivo(job_id: str) -> Optional[bytes]:
    with _CANDADO:
        e = _LOTES.get(job_id)
        return e.get("archivo") if e else None


def _vaciar_para_pruebas() -> None:
    with _CANDADO:
        _LOTES.clear()
