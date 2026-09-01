"""Genera la aplicación web que funciona sin internet.

El resultado es **un solo archivo HTML** con el banco de preguntas adentro. Se
abre con doble clic, funciona sin conexión, se puede copiar al celular por
WhatsApp o por cable, y guarda el avance en el navegador.

Por qué un solo archivo y no una página normal: el estudiante no siempre tiene
datos ni wifi, y un archivo suelto no depende de que ningún servidor esté
prendido. Es la forma más difícil de que el sistema deje de funcionar.
"""

from __future__ import annotations

import json
from pathlib import Path

from .almacen import Configuracion
from .banco import Banco
from .dominio import AREAS, ORDEN_AREAS
from .plan import (
    FASES,
    MINUTOS_POR_BLOQUE,
    MINUTOS_SIMULACRO_COMPLETO,
    PISO_POR_AREA,
    TipoSesion,
)
from .puntaje import CURVA_PUNTAJE, NIVELES_INGLES, SEMAFORO_AREA

#: La plantilla con el HTML, el CSS y el JavaScript de la aplicación.
PLANTILLA: Path = Path(__file__).parent / "plantilla_web.html"

#: Marcas que delimitan el bloque de datos dentro de la plantilla. Se usan DOS
#: (apertura y cierre) a propósito: con una sola, el objeto por defecto de la
#: plantilla quedaba pegado al JSON inyectado y rompía la página entera.
MARCA_INICIO = "/*<DATOS>*/"
MARCA_FIN = "/*</DATOS>*/"


def construir_datos(banco: Banco, config: Configuracion | None = None) -> dict:
    """Arma el diccionario que la aplicación web lleva adentro."""
    preguntas = [
        {
            "id": p.id,
            "area": p.area.value,
            "competencia": p.competencia,
            "componente": p.componente,
            "tema": p.tema,
            "dificultad": p.dificultad.value,
            "contexto": p.contexto,
            "enunciado": p.enunciado,
            "opciones": list(p.opciones),
            "correcta": p.correcta,
            "explicacion": p.explicacion,
            "trampa": p.trampa,
        }
        for p in banco.preguntas
    ]
    areas = {
        area.value: {
            "nombre": AREAS[area].nombre,
            "peso": AREAS[area].peso,
            "preguntas": AREAS[area].preguntas,
            "competencias": list(AREAS[area].competencias),
            "componentes": list(AREAS[area].componentes),
        }
        for area in ORDEN_AREAS
    }
    # La política del plan (fases, mezclas, pisos) se exporta desde Python en vez
    # de reescribirse en JavaScript. Así hay UNA sola fuente de verdad: si aquí
    # cambia una proporción, la aplicación web cambia con ella. Una prueba
    # verifica que lo exportado sea idéntico a las constantes de icfes/plan.py.
    plan = {
        "minutos_bloque": MINUTOS_POR_BLOQUE,
        "minutos_simulacro": MINUTOS_SIMULACRO_COMPLETO,
        "piso_area": PISO_POR_AREA,
        "orden_areas": [a.value for a in ORDEN_AREAS],
        "fases": [
            {
                "nombre": f.nombre,
                "objetivo": f.objetivo,
                "proporcion": f.proporcion,
                "mezcla": [[t.value, p] for t, p in f.mezcla.items()],
            }
            for f in FASES
        ],
        "sesiones": {
            t.value: {"etiqueta": t.etiqueta, "instruccion": t.instruccion} for t in TipoSesion
        },
    }
    escalas = {
        "curva": [list(par) for par in CURVA_PUNTAJE],
        "ingles": [[tope, nivel, desc] for tope, nivel, desc in NIVELES_INGLES],
        "semaforo": [[tope, etq, consejo] for tope, etq, consejo in SEMAFORO_AREA],
    }
    datos: dict = {
        "preguntas": preguntas,
        "areas": areas,
        "plan": plan,
        "escalas": escalas,
        "config": None,
    }
    if config is not None:
        datos["config"] = {
            "examen": config.fecha_examen.isoformat(),
            "meta": config.meta_global,
            "horas": config.horas_semana,
        }
    return datos


def exportar(
    banco: Banco,
    destino: Path,
    config: Configuracion | None = None,
    plantilla: Path | None = None,
) -> Path:
    """Escribe la aplicación web en ``destino`` y devuelve la ruta.

    Args:
        banco: el banco de preguntas que va embebido.
        destino: dónde escribir el archivo HTML.
        config: si se pasa, la app arranca ya configurada con la fecha del
            examen y la meta.
        plantilla: ruta alterna de la plantilla (se usa en las pruebas).
    """
    origen = plantilla or PLANTILLA
    if not origen.is_file():
        raise FileNotFoundError(f"No se encuentra la plantilla web: {origen}")

    html = origen.read_text(encoding="utf-8")
    inicio = html.find(MARCA_INICIO)
    fin = html.find(MARCA_FIN)
    if inicio < 0 or fin < 0 or fin < inicio:
        raise ValueError(
            f"La plantilla debe traer {MARCA_INICIO} … {MARCA_FIN} para inyectar los datos"
        )

    datos = construir_datos(banco, config)
    # ``</script>`` dentro de una cadena JSON cerraría la etiqueta antes de
    # tiempo y rompería la página. Se escapa la barra.
    serializado = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")

    completo = html[: inicio + len(MARCA_INICIO)] + serializado + html[fin:]
    destino = Path(destino)
    if destino.parent != Path():
        destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(completo, encoding="utf-8")
    return destino
