"""Cada ruta que llama el portal tiene que existir en el backend.

Esta es la prueba que le faltaba al repositorio. En `CLAUDE.md` está el caso
que lo enseñó: **la pantalla «Salud Total» estuvo tres meses devolviendo «Not
Found» porque se borró su router sin mirar que el JavaScript seguía
llamándolo.** Nadie se enteró hasta que un auditor lo reportó.

El 20-08-2026, revisando el portal con esta idea, aparecieron tres funciones
muertas por lo mismo:

  · arrastrar una glosa en el **Kanban** llamaba a `POST /glosas/{id}/workflow`
    —el backend solo tiene `PATCH`, y encima ese endpoint es del flujo de
    aprobación, no del estado de la glosa—;
  · **crear y borrar snippets** llamaban a `POST /snippets` y
    `DELETE /snippets/{id}`, que no existían (solo estaba el `GET`);
  · el **simulador de conciliación** llamaba a
    `POST /conciliaciones/{id}/simulador/`, que nunca se implementó.

Los tres fallaban en silencio o con un aviso genérico («No se pudo…»), que es
lo peor: parece un problema de red y nadie lo reporta como defecto.
"""

from __future__ import annotations

import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
PAGINAS = [
    "static/index.html",
    "static/importar-masiva.html",
    "static/importar-recepcion.html",
    "static/preauditoria.html",
]

# api('/a/'+id+'/b', {...})  ·  fetch(`/a/${id}/b`)  ·  api("/a")
_LLAMADA = re.compile(
    r"\b(?:api|fetch)\(\s*"
    r"((?:[`'\"][^`'\"]*[`'\"]|\+|\s|[A-Za-z_$][\w$.]*|\([^()]*\))+?)"
    r"\s*(?:,\s*(\{.{0,400}?\})\s*)?\)",
    re.S,
)


def _rutas_registradas() -> set[tuple[str, str]]:
    from app.main import app

    salida = set()
    for r in app.routes:
        for metodo in getattr(r, "methods", None) or {"GET"}:
            salida.add((metodo, getattr(r, "path", "")))
    return salida


def _patron_de(expr: str) -> str | None:
    """De la expresión JS al patrón de ruta: `'/a/'+id+'/b'` → `/a/{}/b`."""
    trozos = []
    for parte in re.split(r"\+", expr):
        parte = parte.strip()
        literal = re.fullmatch(r"[`'\"]([^`'\"]*)[`'\"]", parte)
        if literal:
            trozos.append(re.sub(r"\$\{[^}]*\}", "{}", literal.group(1)))
        else:
            trozos.append("{}")  # una variable o una llamada
    url = "".join(trozos)
    return url if url.startswith("/") else None


def _casa(seg_ruta: str, seg_url: str) -> bool:
    # Un trozo variable del JS («'/fuentes/'+tipo») puede valer cualquier cosa
    # en ejecución, así que casa tanto con un parámetro de la ruta como con un
    # segmento fijo: en `preauditoria.html`, `tipo` solo vale «radicacion» o
    # «dgreport», y las dos rutas existen escritas literalmente.
    #
    # Esto NO afloja el control donde importa: lo que se busca es si existe
    # ALGUNA ruta a la que esa llamada pueda llegar. Si no existe ninguna, el
    # botón está muerto pase lo que pase. Comprobado volviendo a poner la
    # llamada rota del Kanban: la prueba se pone roja igual.
    if seg_url == "{}":
        return True
    if seg_ruta.startswith("{"):
        return True
    return seg_ruta == seg_url


def _existe(metodo: str, url: str, rutas: set[tuple[str, str]]) -> bool:
    limpia = url.split("?")[0].split("#")[0]
    # Una URL que termina en «{}» suele ser una cadena de parámetros pegada
    # («'/eventos/recientes' + qs»). Se prueba con y sin ese último trozo.
    candidatas = [limpia]
    if limpia.endswith("{}"):
        candidatas.append(limpia[:-2].rstrip("/") or "/")
    for cand in candidatas:
        b = [s for s in cand.strip("/").split("/") if s]
        for m, p in rutas:
            if m != metodo:
                continue
            a = [s for s in p.strip("/").split("/") if s]
            if len(a) == len(b) and all(_casa(x, y) for x, y in zip(a, b)):
                return True
    return False


def _llamadas_de(pagina: str) -> list[tuple[str, str]]:
    texto = (RAIZ / pagina).read_text(encoding="utf-8")
    vistas: set[tuple[str, str]] = set()
    for m in _LLAMADA.finditer(texto):
        url = _patron_de(m.group(1))
        if not url:
            continue
        cuerpo = m.group(2) or ""
        met = re.search(r"method\s*:\s*['\"](\w+)", cuerpo)
        vistas.add((met.group(1).upper() if met else "GET", url))
    return sorted(vistas)


@pytest.mark.parametrize("pagina", PAGINAS)
def test_todas_las_rutas_que_llama_la_pagina_existen(pagina):
    rutas = _rutas_registradas()
    rotas = [(m, u) for m, u in _llamadas_de(pagina) if not _existe(m, u, rutas)]
    assert not rotas, (
        f"{pagina} llama a rutas que el backend no atiende: {rotas}. "
        "El botón va a fallar en silencio o con un «No se pudo…» genérico. "
        "Es el mismo defecto que dejó «Salud Total» tres meses en Not Found."
    )


@pytest.mark.parametrize("pagina", PAGINAS)
def test_la_pagina_si_llama_al_backend(pagina):
    """Si el extractor deja de encontrar llamadas, la prueba de arriba pasaría
    vacía y no vigilaría nada. Esto es el fusible."""
    assert _llamadas_de(pagina), (
        f"No se detectó ni una llamada al backend en {pagina}. "
        "Probablemente cambió la forma de llamar (otro ayudante en vez de "
        "api()/fetch()) y este control quedó ciego."
    )


class TestLosTresBotonesQueEstabanMuertos:
    """Regresión concreta de lo hallado el 20-08-2026."""

    def test_el_kanban_usa_la_ruta_del_estado_de_la_glosa(self):
        texto = (RAIZ / "static/index.html").read_text(encoding="utf-8")
        assert "/estado?nuevo_estado=" in texto, (
            "El Kanban dejó de usar PATCH /glosas/{id}/estado. Con "
            "POST /glosas/{id}/workflow la tarjeta no se movía y salía "
            "«No se pudo cambiar el estado»."
        )

    def test_ya_no_queda_el_post_a_workflow(self):
        texto = (RAIZ / "static/index.html").read_text(encoding="utf-8")
        bloques = re.findall(r"fetch\('/glosas/'\+gid\+'/workflow'.{0,120}", texto, re.S)
        assert not bloques, f"Volvió la llamada rota del Kanban: {bloques}"

    def test_los_cuatro_endpoints_de_snippets_existen(self):
        rutas = _rutas_registradas()
        for metodo, ruta in (
            ("GET", "/snippets"),
            ("POST", "/snippets"),
            ("DELETE", "/snippets/{}"),
            ("POST", "/snippets/{}/usar"),
        ):
            assert _existe(metodo, ruta, rutas), f"Falta {metodo} {ruta}"

    def test_el_simulador_de_conciliacion_existe(self):
        rutas = _rutas_registradas()
        assert _existe("POST", "/conciliaciones/{}/simulador/", rutas)
