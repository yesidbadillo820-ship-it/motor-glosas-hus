"""Saber si hay alguien trabajando en el portal ahora mismo.

POR QUÉ EXISTE (24-08-2026). Pedido de Yesid, textual: «necesito que cada vez
que hagamos cambios y demás no se les esté cayendo la página a los gestores a
cada rato».

El autodespliegue baja el código nuevo cada 5 minutos y, para aplicarlo, apaga
el motor y lo vuelve a levantar. Eso son entre 15 y 30 segundos de página
caída, y cualquier trabajo a medio hacer se pierde: un dictamen que la IA
estaba redactando se va con el motor.

Con esto el autodespliegue puede preguntar antes: si hay alguien trabajando,
espera cinco minutos y vuelve a preguntar. En una oficina de tres personas
siempre aparece un hueco —una llamada, un café, una reunión— y el cambio entra
sin que nadie lo note.

QUÉ CUENTA COMO «ALGUIEN TRABAJANDO»

Una pestaña abierta NO es alguien trabajando. El portal se refresca solo:
pregunta la salud cada 30 segundos, los indicadores del encabezado cada 30, el
estado de la IA cada 5. Si eso contara, una pantalla olvidada encendida el
viernes bloquearía los cambios hasta el lunes.

Entonces cuenta:
  - Todo lo que MODIFICA algo (responder una glosa, subir un archivo, guardar).
  - Las consultas que pidió una persona (abrir una pantalla, buscar, exportar).
Y no cuenta:
  - Lo que el propio portal se pregunta solo cada tanto.
  - Los archivos de la página (imágenes, hojas de estilo).
  - La pregunta que hace el mismo autodespliegue.
"""

from __future__ import annotations

import time

# Cuánto silencio hace falta para dar por hecho que nadie está trabajando.
# 90 segundos: lo bastante para que un hueco normal —contestar el teléfono,
# levantarse por un café— alcance, y lo bastante para no cortarle a alguien
# que está leyendo un dictamen largo antes de decidir.
SEGUNDOS_DE_SILENCIO = 90

# Lo que el portal se pregunta solo, sin que nadie toque nada. Si esto contara,
# una pestaña olvidada abierta mantendría el portal «ocupado» para siempre.
# Los intervalos reales están en static/index.html:
#   /health ............... cada 30 s
#   /analytics/ ........... cada 30 s  (indicadores del encabezado)
#   /notificaciones/badge . cada 60 s
#   /inteligencia/diagnostico  cada 5 min
#   /admin/diagnostico .... cada 5 s
#   /sistema/ia-presence .. cada 5 s
RUTAS_QUE_SE_PIDEN_SOLAS = frozenset(
    {
        "/health",
        "/healthz",
        "/analytics/",
        "/notificaciones/badge",
        "/inteligencia/diagnostico",
        "/admin/diagnostico",
        "/sistema/ia-presence",
        "/sistema/version",
        "/sistema/salud",
        "/sistema/salud/publico",
        "/sistema/ocupacion",
        "/favicon.ico",
    }
)

# Carpetas que no son trabajo de nadie: archivos de la página y documentación.
PREFIJOS_QUE_NO_SON_TRABAJO = ("/static/", "/docs", "/redoc", "/openapi.json")

# Métodos que siempre cuentan: si alguien escribe, alguien está trabajando.
METODOS_QUE_ESCRIBEN = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_ultima_actividad: float = 0.0


def es_trabajo_de_una_persona(metodo: str, ruta: str) -> bool:
    """¿Esta petición la pidió una persona, o se la pidió el portal solo?"""
    if (metodo or "").upper() in METODOS_QUE_ESCRIBEN:
        return True
    ruta = (ruta or "").rstrip("/") or "/"
    for candidata in (ruta, ruta + "/"):
        if candidata in RUTAS_QUE_SE_PIDEN_SOLAS:
            return False
    return not ruta.startswith(PREFIJOS_QUE_NO_SON_TRABAJO)


def marcar_actividad(metodo: str = "GET", ruta: str = "/") -> bool:
    """Deja constancia de que alguien trabajó. Devuelve si se contó."""
    if not es_trabajo_de_una_persona(metodo, ruta):
        return False
    global _ultima_actividad
    _ultima_actividad = time.monotonic()
    return True


def segundos_inactivo() -> float:
    """Cuánto lleva el portal sin que nadie haga nada.

    Recién arrancado devuelve un número grande a propósito: si el motor acaba
    de subir, nadie ha alcanzado a trabajar y no hay nada que interrumpir.
    """
    if not _ultima_actividad:
        return float(SEGUNDOS_DE_SILENCIO * 100)
    return max(0.0, time.monotonic() - _ultima_actividad)


def hay_gente_trabajando() -> bool:
    return segundos_inactivo() < SEGUNDOS_DE_SILENCIO


def reiniciar_para_pruebas() -> None:
    """Solo para las pruebas: olvidar lo que se sabe."""
    global _ultima_actividad
    _ultima_actividad = 0.0
