"""Qué herramientas externas hay en esta máquina, y qué hacer si faltan.

Doce pruebas de esta carpeta necesitan programas que no vienen con Python:
LibreOffice **completo** (Writer, Calc, Draw) y `extract-msg`. Durante meses
fallaron con mensajes que no decían nada —«source file could not be loaded»,
que parece un archivo dañado— y se fueron aceptando como «fallas del
entorno», hasta que dejaron de mirarse.

Acá se separan las dos situaciones, que no son la misma:

* En el PC de quien trabaja, sin esas herramientas, las pruebas **se saltan**
  diciendo qué falta y cómo instalarlo.
* En el CI, donde las herramientas SÍ tienen que estar,
  `EXIGIR_HERRAMIENTAS_DE_PRUEBA=1` convierte ese salto en un **fallo**. Sin
  eso, el día que la instalación del runner se rompa la suite seguiría en
  verde con doce pruebas saltadas y nadie se enteraría.
"""

from __future__ import annotations

import os
import sys

import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SUITE = os.path.join(RAIZ, "tools", "suite_cartera_hus")
if SUITE not in sys.path:
    sys.path.insert(0, SUITE)

COMO_INSTALAR = "Corra:  bash scripts/preparar_entorno_pruebas.sh"


def exigido() -> bool:
    """¿Estamos donde las herramientas son obligatorias (el CI)?"""
    return os.environ.get("EXIGIR_HERRAMIENTAS_DE_PRUEBA", "").strip() in ("1", "true", "TRUE")


def falta_libreoffice() -> str:
    """Motivo por el que LibreOffice no sirve acá; cadena vacía si sirve.

    No basta con que exista el ejecutable: `libreoffice-core` se instala solo
    y deja un `soffice` que arranca pero no puede abrir ni un documento.
    """
    try:
        from nucleo import office_tools
    except Exception as e:  # noqa: BLE001
        return f"no se pudo importar office_tools: {e}"
    if not office_tools.hay_libreoffice():
        return "no está instalado LibreOffice"
    faltan = office_tools.modulos_libreoffice_faltantes()
    if faltan:
        return "LibreOffice incompleto, faltan: " + ", ".join(faltan)
    return ""


def falta_extract_msg() -> str:
    """Motivo por el que `extract-msg` no sirve acá; cadena vacía si sirve."""
    try:
        from nucleo import msg_tools
    except Exception as e:  # noqa: BLE001
        return f"no se pudo importar msg_tools: {e}"
    if msg_tools.extract_msg is None:
        return "no está instalado extract-msg"
    return ""


def _marca(motivo: str, herramienta: str):
    """Marcador de pytest: saltar si la herramienta falta.

    Cuando el CI la exige y no está, esto **revienta al importar**. Es a
    propósito: pytest lo reporta como error de recolección con el motivo
    exacto y el job queda rojo de inmediato. Un `skipif` en esa situación
    dejaría el CI en verde con doce pruebas saltadas, que es justo lo que
    hay que evitar.
    """
    if not motivo:
        return pytest.mark.skipif(False, reason="")
    aviso = f"{herramienta}: {motivo}. {COMO_INSTALAR}"
    if exigido():
        raise RuntimeError(
            aviso + " — EXIGIR_HERRAMIENTAS_DE_PRUEBA=1 está puesta (esto es "
            "el CI): acá la herramienta TIENE que estar, así que esta prueba "
            "no se puede saltar. Si de verdad ya no hace falta, bórrela; no "
            "la deje saltándose en silencio."
        )
    return pytest.mark.skipif(True, reason=aviso)


SIN_LIBREOFFICE = _marca(falta_libreoffice(), "LibreOffice")
SIN_EXTRACT_MSG = _marca(falta_extract_msg(), "extract-msg")
