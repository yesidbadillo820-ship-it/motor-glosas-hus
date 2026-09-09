"""Los iconos de las tres aplicaciones.

Las tres usaban emoji como juego de iconos —40 en el curso de noruego, 15 en el
ICFES, 8 en el de velas—. Se veían a medio terminar por tres razones concretas:
cada teléfono los dibuja distinto, no toman el color del texto (no se pueden
apagar cuando una fila está bloqueada) y no se alinean con la letra que
acompañan.

Ahora las tres llevan un juego propio de SVG incrustado. Estas pruebas evitan
las tres formas de deshacerlo: que vuelva un emoji, que se pida un icono que no
existe —lo que no da error: deja un hueco en blanco— y que alguien vuelva a
llamar `ic` a una variable, que fue lo que tapó la función y dejó la barra de
navegación escribiendo el nombre del icono en vez del dibujo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLANTILLAS = {
    "icfes": Path("icfes/plantilla_web.html"),
    "noruego": Path("noruego/plantilla_web.html"),
    "mercados": Path("mercados/plantilla_web.html"),
}

#: Los rangos de pictogramas. No incluye ✓ ✗ ★ ☆ ▲ ▼ ← → ni demás signos, que
#: son texto de verdad y se dibujan con la fuente de la página.
EMOJI = re.compile(
    r"[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FFℹ⏩-⏺⬀-⯿"
    r"☀-⛿✈-✒✔✖✚-✧✳-✴❄❌"
    r"❓-❕➕-➗➰➿]"
)

LLAMADA = re.compile(r'\bic\(\s*"([a-z-]+)"')
DEFINIDO = re.compile(r'<symbol id="i-([a-z-]+)"')


def sin_comentarios(texto: str) -> str:
    """El código sin comentarios: ahí sí puede quedar un emoji de ejemplo."""
    texto = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    texto = re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", " ", texto)


@pytest.fixture(params=sorted(PLANTILLAS))
def app(request):
    return request.param


def test_ninguna_interfaz_usa_emoji(app):
    sueltos = EMOJI.findall(sin_comentarios(PLANTILLAS[app].read_text(encoding="utf-8")))
    assert not sueltos, (
        f"{app}: volvieron los emoji a la interfaz: {sorted(set(sueltos))}. "
        'Use ic("nombre") con un icono del juego incrustado.'
    )


def test_todo_icono_que_se_pide_existe(app):
    html = PLANTILLAS[app].read_text(encoding="utf-8")
    # Las llamadas se buscan sin comentarios: el ejemplo del propio ayudante
    # —ic("casa")— no es una llamada de verdad.
    faltan = set(LLAMADA.findall(sin_comentarios(html))) - set(DEFINIDO.findall(html))
    assert not faltan, f"{app}: se piden iconos que no existen: {sorted(faltan)}"


def test_ningun_icono_sobra(app):
    """Un icono que ya nadie usa es peso muerto en un archivo que va al celular."""
    html = PLANTILLAS[app].read_text(encoding="utf-8")
    definidos = set(DEFINIDO.findall(html))
    # Hay nombres que viajan como dato (la barra de navegación y los logros los
    # llevan dentro de un arreglo), así que basta con que el nombre aparezca
    # entrecomillado en alguna parte de la plantilla.
    usados = {n for n in definidos if f'"{n}"' in html}
    if app == "noruego":
        from noruego.curso import MODULOS

        usados |= {m.icono for m in MODULOS}
    assert not definidos - usados, f"{app}: iconos que nadie usa: {sorted(definidos - usados)}"


def test_los_iconos_no_se_piden_por_internet(app):
    """Las tres funcionan sin señal: el juego va dentro del archivo."""
    html = PLANTILLAS[app].read_text(encoding="utf-8")
    assert '<use href="#i-' in html, f"{app}: los iconos no apuntan al juego incrustado"
    assert not re.search(r'<use[^>]+href="(?!#)', html), f"{app}: un icono se pide de fuera"


def test_nadie_tapa_la_funcion_ic(app):
    """`([id,ic,t])` en la barra dejaba tapada la función `ic` y salía escrito
    el nombre del icono en vez del dibujo."""
    html = PLANTILLAS[app].read_text(encoding="utf-8")
    assert len(re.findall(r"function ic\(", html)) == 1, f"{app}: la función ic() no es única"
    assert not re.search(r"\(\s*\[[^\]]*\bic\b[^\]]*\]\s*\)\s*=>", html), (
        f"{app}: una desestructuración usa `ic` como nombre y taparía a la función"
    )
    assert not re.search(r"\b(?:const|let|var)\s+ic\s*=", html), (
        f"{app}: una variable se llama `ic` y taparía a la función"
    )
