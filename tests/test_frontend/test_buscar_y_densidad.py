"""Buscar dentro de la tabla, y filas compactas para revisar lotes.

26-08-2026, de las propuestas al motor.

BUSCAR. «Mis glosas» tenia pestanas, presets y vista kanban — pero ningun
campo para buscar. En el lote de COOSALUD, con 1.573 facturas, encontrar una
pasando paginas es inviable. El filtro corre sobre lo que YA esta pintado: es
instantaneo y no gasta una llamada al motor.

DENSIDAD. Las filas estan hechas para leerse comodas, no para revisar
doscientas seguidas. El gestor pasa el dia en esas listas, asi que la
preferencia se recuerda.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    return INDEX.read_text(encoding="utf-8")


class TestElBuscador:
    def test_existe_el_campo(self, html):
        assert 'id="mis-buscar"' in html

    def test_dice_que_se_puede_buscar(self, html):
        assert "Buscar factura, EPS, código" in html

    def test_filtra_al_escribir_sin_llamar_al_servidor(self, html):
        assert 'oninput="filtrarMisGlosas()"' in html
        i = html.index("function filtrarMisGlosas()")
        cuerpo = html[i : i + 1200]
        assert "fetch(" not in cuerpo, "el filtro corre sobre lo ya pintado"

    def test_dice_cuantas_quedaron(self, html):
        assert 'id="mis-buscar-cuenta"' in html

    def test_tiene_etiqueta_para_lectores_de_pantalla(self, html):
        assert 'aria-label="Buscar en mis glosas"' in html


class TestLaDensidad:
    def test_existe_el_interruptor(self, html):
        assert 'id="btn-densidad"' in html
        assert "function alternarDensidad()" in html

    def test_se_recuerda_por_usuario(self, html):
        i = html.index("function alternarDensidad()")
        assert "localStorage" in html[i : i + 700]
        assert "recordarDensidad" in html

    def test_el_css_aprieta_las_filas(self, html):
        assert "body.denso table td" in html

    def test_leer_lo_guardado_no_puede_tumbar_la_pagina(self, html):
        """En una ventana privada localStorage lanza excepción."""
        i = html.index("function recordarDensidad()")
        cuerpo = html[i : i + 600]
        assert "try{" in cuerpo and "catch" in cuerpo


class TestElSelloDiceContraQueVerifico:
    """El sello decía «N citas contra corpus · 0 hallazgos» sin decir nunca qué
    tan de fiar era ese corpus. Esa semana se descubrió que 21 de las 26 normas
    tenían algún artículo inventado."""

    def test_el_sello_muestra_la_hoja_de_vida_del_corpus(self, html):
        assert "v.corpus && v.corpus.leyenda" in html

    def test_si_queda_una_norma_sin_verificar_el_sello_baja_de_grado(self, html):
        i = html.index("v.corpus && v.corpus.leyenda")
        cuerpo = html[i : i + 400]
        assert "normas_sin_verificar" in cuerpo
        assert "CORPUS INCOMPLETO" in cuerpo


class TestLosAvisosSeImprimen:
    def test_la_hoja_de_impresion_los_deja_ver(self, html):
        i = html.index("@media print{")
        cuerpo = html[i : i + 3000]
        assert ".aviso-no-radicar" in cuerpo

    def test_y_en_rojo(self, html):
        i = html.index("@media print{")
        cuerpo = html[i : i + 3000]
        j = cuerpo.index(".aviso-no-radicar")
        assert "#dc2626" in cuerpo[j : j + 400]
