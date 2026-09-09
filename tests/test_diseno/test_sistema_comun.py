"""El sistema de diseño común a las tres aplicaciones.

ICFES, noruego y velas japonesas son tres programas independientes, pero para
quien las usa son tres pantallas del mismo autor. Antes cada una traía su
propio acabado y se notaba: tres tipografías, tres formas de botón, tres
maneras de marcar la pestaña activa.

Ahora las tres llevan **el mismo bloque de CSS, carácter por carácter**, y cada
una solo traduce sus colores a los nombres del sistema (los tokens `--ds-*`).
Estas pruebas sostienen ese trato. Sin ellas, la primera corrección urgente en
una de las tres las vuelve a separar sin que nadie lo note.
"""

from __future__ import annotations

import re
from pathlib import Path

PLANTILLAS = {
    "icfes": Path("icfes/plantilla_web.html"),
    "noruego": Path("noruego/plantilla_web.html"),
    "mercados": Path("mercados/plantilla_web.html"),
}

TITULO = "SISTEMA DE DISEÑO COMÚN"

#: Los nombres que el sistema usa y que cada aplicación debe traducir.
PUENTE = (
    "--ds-sup",
    "--ds-linea",
    "--ds-tinta3",
    "--ds-acento",
    "--ds-acento-hondo",
    "--ds-vidrio",
    "--ds-luz1",
    "--ds-luz2",
    "--ds-r2",
    "--ds-r3",
    "--ds-hueco",
    "--ds-e2",
    "--ds-e3",
)


def bloque_del_sistema(html: str) -> str:
    inicio = html.index(TITULO)
    return html[inicio : html.index("</style>", inicio)]


def texto(app: str) -> str:
    return PLANTILLAS[app].read_text(encoding="utf-8")


def test_las_tres_llevan_el_mismo_sistema_palabra_por_palabra():
    bloques = {app: bloque_del_sistema(texto(app)) for app in PLANTILLAS}
    referencia = bloques["icfes"]
    distintas = [app for app, b in bloques.items() if b != referencia]
    assert not distintas, (
        f"el sistema de diseño se separó en: {distintas}. Un arreglo en una de "
        "las tres pantallas va en las tres, o vuelven a parecer tres productos."
    )


def test_cada_aplicacion_traduce_todos_los_nombres_del_sistema():
    """Un token sin traducir no da error: la regla simplemente no se aplica."""
    for app in PLANTILLAS:
        html = texto(app)
        antes = html[: html.index(TITULO)]
        faltan = [t for t in PUENTE if f"{t}:" not in antes]
        assert not faltan, f"{app} no traduce: {faltan}"


def test_el_sistema_usa_solo_nombres_que_el_puente_define():
    """Si el sistema pide un `--ds-` que nadie define, la regla queda muerta."""
    sistema = bloque_del_sistema(texto("icfes"))
    pedidos = set(re.findall(r"var\((--ds-[a-z0-9-]+)", sistema))
    assert not (pedidos - set(PUENTE)), (
        f"el sistema pide nombres sin puente: {pedidos - set(PUENTE)}"
    )


def test_la_luz_del_fondo_no_le_pisa_la_posicion_a_la_barra():
    """El error que costó una corrida: levantar el contenido con
    `position:relative` para dejarlo encima del fondo le pisa el
    `position:fixed` a la barra de abajo, y deja de quedarse pegada."""
    for app in PLANTILLAS:
        estilo = texto(app).split("<style>", 1)[1].split("</style>", 1)[0]
        for selector, cuerpo in re.findall(r"([^{}]*)\{([^{}]*)\}", estilo):
            # Solo importan las reglas que apuntan a la barra MISMA. `.nav
            # button{position:relative}` es legítimo: posiciona el botón.
            apunta = any(
                re.fullmatch(r"\.nav(::?[a-z-]+(\([^)]*\))?)*", parte.split()[-1])
                for parte in selector.split(",")
                if parte.split()
            )
            if not apunta:
                continue
            posicion = re.findall(r"position\s*:\s*([a-z]+)", cuerpo)
            assert "relative" not in posicion and "static" not in posicion, (
                f"{app}: la regla «{selector.strip()}» le quita el fixed a la barra"
            )


def test_el_movimiento_se_apaga_si_el_sistema_lo_pide():
    for app in PLANTILLAS:
        assert "prefers-reduced-motion:reduce" in texto(app), app


def test_el_foco_siempre_se_ve():
    """Quien navega con teclado tiene que saber dónde está parado."""
    for app in PLANTILLAS:
        assert ":focus-visible" in texto(app), app
