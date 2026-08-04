"""Las herramientas del Centro de Automatización tienen que VIAJAR a producción.

Lo que pasó: `.dockerignore` excluía `tools/` completa (regla de cuando ahí
solo vivían bots de PC), así que la imagen Docker salía sin los módulos que
el Centro de Automatización importa. En local todo verde; en la VM, todas
las tarjetas contestaban «ModuleNotFoundError». Esta guardia amarra el
catálogo a la lista blanca del `.dockerignore`: si alguien agrega la
automatización #8 y olvida la línea `!tools/...`, la suite lo dice acá.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services import automatizaciones as svc

_RAIZ = Path(__file__).resolve().parent.parent.parent


def _lineas_dockerignore() -> list[str]:
    texto = (_RAIZ / ".dockerignore").read_text(encoding="utf-8")
    return [ln.strip() for ln in texto.splitlines() if ln.strip() and not ln.startswith("#")]


def test_cada_modulo_del_catalogo_esta_en_la_lista_blanca():
    lineas = _lineas_dockerignore()
    if "tools/" not in lineas:
        return  # si tools/ no se excluye, todo viaja y no hay nada que vigilar

    modulos = {a.modulo for a in svc.CATALOGO} | {"_dinero"}
    faltantes = [m for m in modulos if f"!tools/{m}.py" not in lineas]
    assert not faltantes, (
        "Estos módulos del Centro de Automatización NO viajan en la imagen "
        f"Docker (falta su '!tools/<modulo>.py' en .dockerignore): {sorted(faltantes)}. "
        "En producción responderían ModuleNotFoundError."
    )


def test_los_modulos_de_la_lista_blanca_existen():
    """La inversa: una línea blanca apuntando a un archivo borrado es un
    catálogo que promete una herramienta que ya no está."""
    for ln in _lineas_dockerignore():
        m = re.fullmatch(r"!tools/([A-Za-z0-9_]+\.py)", ln)
        if m:
            assert (_RAIZ / "tools" / m.group(1)).exists(), (
                f"{ln} apunta a un archivo que no existe"
            )


def test_el_dockerfile_copia_tools():
    dockerfile = (_RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^COPY tools/ ", dockerfile, re.M), (
        "El Dockerfile ya no copia tools/: el Centro de Automatización quedaría sin motor"
    )
