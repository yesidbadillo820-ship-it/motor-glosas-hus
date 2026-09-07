"""El texto del libro para cada patrón, separado del código que lo detecta.

Igual que el léxico del curso de noruego: el contenido vive en JSON para que
se pueda corregir o ampliar sin tocar programación, y un revisor comprueba que
no falte nada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .patrones import PATRONES, POR_CLAVE

CARPETA = Path(__file__).parent / "catalogo"
ARCHIVO = CARPETA / "patrones.json"

#: Campos que toda ficha tiene que traer. Sin ellos la pantalla queda coja.
OBLIGATORIOS = ("clave", "pagina", "identificar", "significado")


@dataclass(frozen=True)
class Ficha:
    """Lo que el libro dice de un patrón."""

    clave: str
    pagina: int
    identificar: tuple[str, ...]
    significado: str
    revisar: str | None = None


@lru_cache(maxsize=1)
def cargar() -> dict[str, Ficha]:
    crudo = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    fichas = {}
    for f in crudo["patrones"]:
        fichas[f["clave"]] = Ficha(
            clave=f["clave"],
            pagina=int(f["pagina"]),
            identificar=tuple(f["identificar"]),
            significado=f["significado"],
            revisar=f.get("revisar"),
        )
    return fichas


@lru_cache(maxsize=1)
def fuente() -> dict[str, str]:
    return json.loads(ARCHIVO.read_text(encoding="utf-8"))["fuente"]


def revisar() -> list[str]:
    """Avisos: fichas incompletas, sobrantes o patrones sin ficha."""
    crudo = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    avisos: list[str] = []
    vistas = set()
    for f in crudo["patrones"]:
        clave = f.get("clave", "(sin clave)")
        vistas.add(clave)
        faltan = [c for c in OBLIGATORIOS if not f.get(c)]
        if faltan:
            avisos.append(f"«{clave}»: le falta {', '.join(faltan)}")
        if clave not in POR_CLAVE:
            avisos.append(f"«{clave}»: hay ficha pero no hay detector")
        if f.get("identificar") and len(f["identificar"]) < 2:
            avisos.append(f"«{clave}»: la lista de cómo identificarlo tiene una sola línea")
    for patron in PATRONES:
        if patron.clave not in vistas:
            avisos.append(f"«{patron.clave}»: hay detector pero no hay ficha en el catálogo")
    return avisos
