"""Cuánto tarda cada pantalla del motor. Para dejar de adivinar.

11-09-2026. Yesid: «*ayúdame a mirar por qué está tan lenta la plataforma*».
Y no había con qué: el motor **no anotaba en ninguna parte cuánto tardaba en
contestar**. Se podía mirar la memoria, el procesador y el servidor de
archivos —y se miró— pero no lo único que de verdad contesta la pregunta:
**qué pantalla es la lenta**.

Sin eso, cada vez que la plataforma se pone pesada toca salir a suponer. Esto
lo convierte en un dato:

  · Se cronometra cada petición (cuesta microsegundos, no se nota).
  · Las que pasan de `SEGUNDOS_PARA_AVISAR` quedan anotadas en el registro
    con nombre y apellido, para verlas después aunque nadie estuviera mirando.
  · Y se guarda un resumen por pantalla —cuántas veces, cuánto tardó en
    promedio, cuál fue la peor— que se ve en «Diagnóstico del sistema».

MEMORIA. Todo vive en RAM y está acotado a propósito: el motor del hospital
ya anda por el gigabyte y esto no puede sumar. Las rutas se agrupan (todas
las glosas caen en `/glosas/{n}`, no una entrada por glosa) y hay un tope de
`MAX_RUTAS`; de las lentas se guardan solo las últimas `MAX_RECIENTES`.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from typing import Any, Optional

from app.core.logging_utils import logger

# Por encima de esto, la petición queda anotada en el registro. Dos segundos
# es lo que un auditor ya siente como «se quedó pensando».
SEGUNDOS_PARA_AVISAR = 2.0

MAX_RUTAS = 400
MAX_RECIENTES = 50

# `/glosas/12345` y `/glosas/99` son la MISMA pantalla. Sin agrupar, cada
# glosa abierta sería una fila distinta y el resumen no diría nada —además de
# comerse la memoria.
_RE_NUMERO = re.compile(r"/\d+")
_RE_UUID = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_RE_FACTURA = re.compile(r"/HUS\d+", re.IGNORECASE)


def agrupar_ruta(ruta: str) -> str:
    """`/soportes-auto/factura/HUS0000541440` → `/soportes-auto/factura/{factura}`."""
    r = _RE_UUID.sub("/{id}", ruta or "/")
    r = _RE_FACTURA.sub("/{factura}", r)
    r = _RE_NUMERO.sub("/{n}", r)
    return r[:120]


class _Reloj:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._por_ruta: dict[str, dict[str, Any]] = {}
        self._recientes: deque[dict[str, Any]] = deque(maxlen=MAX_RECIENTES)
        self._desde = time.time()
        self._total = 0
        self._lentas = 0

    def anotar(self, metodo: str, ruta: str, estado: int, segundos: float) -> None:
        clave = f"{metodo} {agrupar_ruta(ruta)}"
        lenta = segundos >= SEGUNDOS_PARA_AVISAR
        with self._lock:
            self._total += 1
            fila = self._por_ruta.get(clave)
            if fila is None:
                # Tope duro: si ya hay demasiadas rutas distintas, no se
                # agregan más. Vale más un resumen incompleto que un motor
                # que se come la memoria por medir.
                if len(self._por_ruta) >= MAX_RUTAS:
                    return
                fila = {"veces": 0, "total_s": 0.0, "peor_s": 0.0, "lentas": 0}
                self._por_ruta[clave] = fila
            fila["veces"] += 1
            fila["total_s"] += segundos
            if segundos > fila["peor_s"]:
                fila["peor_s"] = segundos
            if lenta:
                fila["lentas"] += 1
                self._lentas += 1
                self._recientes.append(
                    {
                        "cuando": time.time(),
                        "metodo": metodo,
                        "ruta": ruta[:200],
                        "estado": estado,
                        "segundos": round(segundos, 2),
                    }
                )
        if lenta:
            logger.warning(f"[LENTITUD] {metodo} {ruta} tardó {segundos:.1f}s (estado {estado})")

    def resumen(self, limite: int = 20) -> dict[str, Any]:
        with self._lock:
            filas = [
                {
                    "ruta": clave,
                    "veces": f["veces"],
                    "promedio_s": round(f["total_s"] / f["veces"], 3) if f["veces"] else 0.0,
                    "peor_s": round(f["peor_s"], 2),
                    "lentas": f["lentas"],
                }
                for clave, f in self._por_ruta.items()
            ]
            recientes = list(self._recientes)
            desde, total, lentas = self._desde, self._total, self._lentas
        # Manda lo que MÁS TIEMPO se lleva en total, no lo que más tarda una
        # vez: una pantalla de 0,4 s que se abre mil veces pesa más en el día
        # del auditor que una de 8 s que se abre una.
        filas.sort(key=lambda f: f["promedio_s"] * f["veces"], reverse=True)
        return {
            "midiendo_desde_seg": round(time.time() - desde),
            "peticiones": total,
            "peticiones_lentas": lentas,
            "umbral_seg": SEGUNDOS_PARA_AVISAR,
            "por_pantalla": filas[:limite],
            "ultimas_lentas": list(reversed(recientes)),
        }

    def reiniciar(self) -> None:
        with self._lock:
            self._por_ruta.clear()
            self._recientes.clear()
            self._desde = time.time()
            self._total = 0
            self._lentas = 0


_reloj = _Reloj()


def anotar(metodo: str, ruta: str, estado: int, segundos: float) -> None:
    _reloj.anotar(metodo, ruta, estado, segundos)


def resumen(limite: int = 20) -> dict[str, Any]:
    return _reloj.resumen(limite)


def reiniciar() -> None:
    """Vuelve a empezar la cuenta. Útil para medir un rato concreto."""
    _reloj.reiniciar()


def cronometrar(metodo: str, ruta: str) -> "_Cronometro":
    return _Cronometro(metodo, ruta)


class _Cronometro:
    def __init__(self, metodo: str, ruta: str) -> None:
        self.metodo = metodo
        self.ruta = ruta
        self.estado: Optional[int] = None
        self._t0 = 0.0

    def __enter__(self) -> "_Cronometro":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_a: Any) -> None:
        anotar(self.metodo, self.ruta, self.estado or 0, time.perf_counter() - self._t0)
