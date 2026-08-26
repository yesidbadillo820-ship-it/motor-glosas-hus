"""La pantalla «Mi día».

Idea del 26-08-2026: 32 pantallas para un gestor que en el día a día hace
tres cosas. Esta es la pantalla de entrada con esas tres y nada más.

Lo que se revisa aquí es lo que le pasa al gestor delante de la pantalla:
que las tres columnas estén, que la plata salga con el formato único, que si
el servidor no responde se lo digan, que las tres columnas tengan qué decir
cuando están vacías, y —lo que más importa— que un plazo que el motor no
conoce se muestre como desconocido y no como si venciera hoy.
"""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture(scope="module")
def html() -> str:
    return pathlib.Path("static/index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js(html: str) -> str:
    ini = html.find("// ─── «MI DÍA» (26-08-2026)")
    assert ini > 0, "se perdió el bloque de «Mi día»"
    fin = html.find("// ─── TABLERO DE PLATA RECUPERADA", ini)
    assert fin > ini
    return html[ini:fin]


class TestLaPantallaExiste:
    def test_hay_panel_y_boton_de_menu(self, html: str):
        assert 'id="p-mi-dia"' in html
        assert "sidebarTab(this,'mi-dia')" in html

    def test_al_entrar_se_carga(self, html: str):
        assert "if(id==='mi-dia') cargarMiDia();" in html

    def test_la_ve_cualquier_gestor(self, html: str):
        ini = html.find('id="sn-mi-dia"')
        assert ini > 0
        boton = html[max(0, ini - 400) : ini + 60]
        assert "data-solo-coordinacion" not in boton, (
            "«Mi día» es la pantalla de entrada del gestor: no puede estar reservada a coordinación"
        )


class TestLasTresColumnas:
    @pytest.mark.parametrize("caja", ["midia-responder", "midia-revisar", "midia-radicar"])
    def test_cada_columna_tiene_su_caja(self, html: str, caja: str):
        assert f'id="{caja}"' in html

    def test_los_titulos_dicen_lo_que_hay_que_hacer(self, html: str):
        for titulo in (
            "Responder lo que llegó",
            "Revisar lo que el motor marcó",
            "Radicar lo que está listo",
        ):
            assert titulo in html, f"falta el título «{titulo}»"

    def test_cada_columna_dice_algo_cuando_esta_vacia(self, js: str):
        assert "Nada por responder" in js
        assert "no marcó nada" in js
        assert "Nada aprobado" in js


class TestElPlazoNoSeInventa:
    def test_sin_plazo_se_dice_sin_plazo(self, js: str):
        assert "sin plazo conocido" in js, (
            "una glosa sin fecha no puede pintarse como si venciera hoy"
        )

    def test_el_plazo_del_contador_se_advierte(self, js: str):
        assert "plazo_sin_fecha" in js
        assert "sin fecha" in js, (
            "si el plazo salió del contador y no de una fecha, hay que decirlo"
        )

    def test_lo_vencido_se_ve_en_rojo(self, js: str):
        assert "vencida hace" in js
        assert "--c-red" in js


class TestLaPlataYLosErrores:
    def test_usa_el_formato_unico(self, js: str):
        assert "fmtCOP(" in js
        assert "toLocaleString" not in js

    def test_si_no_carga_se_avisa(self, js: str):
        assert "avisarNoCargo(" in js, (
            "si el servidor no responde, tres columnas vacías se leen como "
            "«hoy no tengo nada que hacer»"
        )

    def test_hay_estado_de_carga(self, js: str):
        assert "Cargando…" in js

    def test_el_texto_de_la_glosa_se_escapa(self, js: str):
        assert "escHtml(g.factura" in js and "escHtml(g.eps" in js, (
            "la factura y la EPS vienen de un Excel de la entidad: van escapadas"
        )

    def test_avisa_cuando_hay_mas_de_las_que_muestra(self, js: str):
        assert "hay_mas" in js and "Mis glosas" in js, (
            "si la columna se corta, el gestor tiene que saber dónde está el resto"
        )
