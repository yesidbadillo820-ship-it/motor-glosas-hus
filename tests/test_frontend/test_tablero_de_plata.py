"""La pantalla del tablero de plata recuperada.

Idea del 26-08-2026: había 32 pantallas y una sola gráfica. El motor sabía
cuánto se glosó, cuánto se respondió y cuánto se levantó, pero eso no se veía
junto en ninguna parte.

Lo que se revisa aquí es lo que le puede pasar al auditor delante de la
pantalla: que la plata salga con el formato único, que si el servidor no
responde se lo digan en vez de dejarle ceros, y que el aviso de «esto no lo
puedo afirmar» tenga dónde salir.
"""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture(scope="module")
def html() -> str:
    return pathlib.Path("static/index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_del_tablero(html: str) -> str:
    ini = html.find("async function cargarPlata()")
    assert ini > 0, "se perdió la función que carga el tablero"
    fin = html.find("\n// ─── HISTORIAL", ini)
    assert fin > ini
    return html[ini:fin]


class TestLaPantallaExiste:
    def test_hay_panel_y_esta_en_el_menu(self, html: str):
        assert 'id="p-plata"' in html, "falta el panel del tablero"
        assert "sidebarTab(this,'plata')" in html, "falta el botón del menú"

    def test_el_menu_lo_deja_solo_a_coordinacion(self, html: str):
        ini = html.find('id="sn-plata"')
        assert ini > 0
        boton = html[max(0, ini - 400) : ini + 60]
        assert 'data-solo-coordinacion="1"' in boton, (
            "el endpoint exige COORDINADOR o SUPER_ADMIN: el botón no puede "
            "quedar visible para quien va a recibir un 403"
        )

    def test_al_entrar_al_panel_se_carga(self, html: str):
        assert "if(id==='plata') cargarPlata();" in html, "el panel quedaría en blanco al abrirlo"


class TestLaPlataSeVeComoPlata:
    def test_usa_el_formato_unico(self, js_del_tablero: str):
        assert "fmtCOP(" in js_del_tablero
        assert "toLocaleString" not in js_del_tablero, (
            "la moneda va con fmtCOP, no con toLocaleString suelto"
        )

    def test_las_cinco_cifras_de_la_gerencia_estan(self, html: str):
        for campo in (
            "plata-glosado",
            "plata-levantado",
            "plata-ratificado",
            "plata-perdido",
            "plata-sindec",
            "plata-tasa",
        ):
            assert f'id="{campo}"' in html, f"falta la casilla {campo}"


class TestSiNoCargaSeAvisa:
    def test_el_error_se_le_dice_al_auditor(self, js_del_tablero: str):
        assert "avisarNoCargo(" in js_del_tablero, (
            "si el servidor no responde, el auditor no puede quedarse mirando "
            "un tablero en ceros creyendo que no se glosó nada"
        )

    def test_hay_estado_de_carga(self, js_del_tablero: str):
        assert "'…'" in js_del_tablero, "falta el estado de carga en las casillas"

    def test_hay_estado_vacio_en_las_tablas(self, html: str):
        assert "No hay glosas en el periodo escogido." in html


class TestElTableroDiceLoQueNoPuedeAfirmar:
    def test_hay_donde_avisar_lo_que_falta(self, html: str):
        assert 'id="plata-faltantes"' in html
        assert "_plataAvisarFaltantes" in html

    def test_avisa_la_levantada_sin_valor_anotado(self, html: str):
        ini = html.find("function _plataAvisarFaltantes")
        assert ini > 0
        bloque = html[ini : ini + 2000]
        assert "levantadas_sin_valor" in bloque
        assert "NO está sumada" in bloque, (
            "hay que decirle al auditor que esa plata no entró en el total, "
            "no dejarlo suponiendo que sí"
        )

    def test_avisa_lo_que_no_tiene_fecha(self, html: str):
        ini = html.find("function _plataAvisarFaltantes")
        bloque = html[ini : ini + 2000]
        assert "sin_fecha_vencimiento" in bloque
        assert "sin_fecha_radicacion" in bloque
