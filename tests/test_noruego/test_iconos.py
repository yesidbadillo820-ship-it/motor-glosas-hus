"""Los iconos de la aplicación: que existan y que no vuelvan los emoji.

La aplicación se veía a medio terminar porque 40 emoji distintos hacían de
juego de iconos: se dibujan diferente en cada teléfono, no toman el color del
texto y ninguno se puede alinear con la tipografía. Se cambiaron por un juego
propio de SVG incrustado. Estas pruebas evitan las dos formas de deshacerlo:
volver a meter un emoji, o pedir un icono que no existe —que no falla, solo
deja un hueco en blanco que nadie nota hasta que el auditor abre la pantalla.
"""

from __future__ import annotations

import re
from pathlib import Path

PLANTILLA = Path("noruego/plantilla_web.html")
CURSO = Path("noruego/curso.py")

#: Los rangos de emoji. No incluye ✓ ✕ ★ ← → y demás signos tipográficos, que
#: son texto de verdad y se dibujan con la fuente.
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF☀-➿\u23E9-\u23FA\u2B00-\u2BFF]")

#: `ic("nombre")` — la llamada que dibuja un icono.
LLAMADA = re.compile(r'\bic\(\s*"([a-z-]+)"')

#: `<symbol id="i-nombre">` — el icono en el juego incrustado.
DEFINIDO = re.compile(r'<symbol id="i-([a-z-]+)"')


def sin_comentarios(texto: str) -> str:
    """El código sin comentarios: ahí sí puede quedar un emoji de ejemplo."""
    texto = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    texto = re.sub(r"/\*.*?\*/", " ", texto, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", " ", texto)


def test_la_interfaz_no_usa_ni_un_emoji():
    sueltos = EMOJI.findall(sin_comentarios(PLANTILLA.read_text(encoding="utf-8")))
    assert not sueltos, (
        f"volvieron los emoji a la interfaz: {sorted(set(sueltos))}. "
        'Use ic("nombre") con un icono del juego incrustado.'
    )


def test_los_modulos_del_curso_tampoco():
    sueltos = EMOJI.findall(CURSO.read_text(encoding="utf-8"))
    assert not sueltos, f"el módulo trae un emoji por icono: {sorted(set(sueltos))}"


def test_todo_icono_que_se_pide_existe_en_el_juego():
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    definidos = set(DEFINIDO.findall(plantilla))
    pedidos = set(LLAMADA.findall(plantilla))
    faltan = pedidos - definidos
    assert not faltan, f"se piden iconos que no existen: {sorted(faltan)}"


def test_los_iconos_de_los_modulos_existen_en_el_juego():
    """El icono del módulo viaja como dato: si nadie lo mira, sale en blanco."""
    definidos = set(DEFINIDO.findall(PLANTILLA.read_text(encoding="utf-8")))
    from noruego.curso import MODULOS

    faltan = {m.icono for m in MODULOS} - definidos
    assert not faltan, f"módulos con icono inexistente: {sorted(faltan)}"


def test_ningun_icono_del_juego_sobra():
    """Un icono que ya nadie usa es peso muerto en un archivo que va al celular."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    from noruego.curso import MODULOS

    # Hay nombres que viajan como dato —la barra de navegación y los logros los
    # llevan dentro de un arreglo—, así que vale con que el nombre aparezca
    # entrecomillado en alguna parte de la plantilla.
    definidos = set(DEFINIDO.findall(plantilla))
    usados = {n for n in definidos if f'"{n}"' in plantilla} | {m.icono for m in MODULOS}
    sobran = definidos - usados
    assert not sobran, f"iconos definidos que nadie usa: {sorted(sobran)}"


def test_el_juego_de_iconos_no_pide_nada_por_internet():
    """La aplicación funciona sin señal: los iconos van dentro del archivo."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    assert '<use href="#i-' in plantilla, "los iconos ya no apuntan al juego incrustado"
    assert not re.search(r'<use[^>]+href="(?!#)', plantilla), "un icono se pide de fuera"


def test_la_variable_del_icono_no_tapa_la_funcion():
    """`([id,ic,t])` en la barra de navegación dejaba la función `ic` tapada y
    la barra salía con el nombre del icono escrito en vez del dibujo."""
    plantilla = PLANTILLA.read_text(encoding="utf-8")
    for declaracion in re.findall(r"(?:const|let|var|function)\s+ic\b", plantilla):
        del declaracion  # solo cuenta
    assert len(re.findall(r"function ic\(", plantilla)) == 1
    assert not re.search(r"\(\s*\[[^\]]*\bic\b[^\]]*\]\s*\)\s*=>", plantilla), (
        "una desestructuración usa `ic` como nombre y taparía a la función ic()"
    )
