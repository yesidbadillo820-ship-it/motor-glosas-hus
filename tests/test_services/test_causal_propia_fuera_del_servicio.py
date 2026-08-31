"""El código de la glosa que se está contestando no es el del servicio.

PRUEBA 2 DE ESTRÉS (31-08-2026), segunda corrida — glosa CL4506, factura
HUS0000601892. El recuadro salió con:

    Servicio objetado: OSTEOSÍNTESIS DE FÉMUR código CL4506

CL4506 es la causal que la entidad invocó, no el procedimiento que el hospital
prestó. Presentarla como código del servicio le muestra a NUEVA EPS que el
escrito confunde su propia objeción con lo facturado.

La red del 28-08 ya existía y estaba bien; el filtro era muy estrecho: solo
borraba el código si figuraba EXACTO en el catálogo de 200 causales, y CL4506
no está entre ellas. Ahora también se borra el código de la glosa que se está
contestando, que no necesita catálogo: por definición es la causal.
"""

import pytest

from app.services.glosa_service import _es_codigo_de_glosa, _quitar_causal_del_servicio


class TestElCasoQueLoDestapo:
    def test_quita_el_codigo_de_esta_glosa_aunque_no_este_en_el_catalogo(self):
        assert not _es_codigo_de_glosa("CL4506"), (
            "si CL4506 entró al catálogo, esta prueba ya no comprueba lo que cree"
        )
        r = _quitar_causal_del_servicio("OSTEOSÍNTESIS DE FÉMUR código CL4506", "CL4506")
        assert r == "OSTEOSÍNTESIS DE FÉMUR"

    def test_sin_el_codigo_de_la_glosa_se_comporta_como_antes(self):
        """Sin saber cuál se contesta, no se acusa a un código desconocido."""
        entrada = "OSTEOSÍNTESIS DE FÉMUR código CL4506"
        assert _quitar_causal_del_servicio(entrada) == entrada


class TestLoDel28DeAgostoSigueIgual:
    def test_el_catalogo_sigue_mandando_para_los_demas(self):
        r = _quitar_causal_del_servicio("CONSULTA DE PRIMERA VEZ, código SO0102")
        assert r == "CONSULTA DE PRIMERA VEZ"

    def test_el_catalogo_manda_aunque_se_conteste_otra_glosa(self):
        r = _quitar_causal_del_servicio("CONSULTA DE PRIMERA VEZ, código SO0102", "TA0301")
        assert r == "CONSULTA DE PRIMERA VEZ"


class TestNoSeLlevaPorDelanteLoQueNoEs:
    def test_no_toca_un_cups_de_verdad(self):
        entrada = "HEMOGRAMA IV código 902210"
        assert _quitar_causal_del_servicio(entrada, "CL4506") == entrada

    def test_no_borra_el_servicio_entero(self):
        """Si al quitar el código no queda nada, se devuelve lo que había."""
        assert _quitar_causal_del_servicio("código CL4506", "CL4506") == "código CL4506"

    def test_servicio_vacio_no_rompe(self):
        assert _quitar_causal_del_servicio("", "CL4506") == ""

    @pytest.mark.parametrize("variante", ["CL-4506", "CL 4506", "cl4506"])
    def test_aguanta_guiones_espacios_y_minusculas(self, variante: str):
        r = _quitar_causal_del_servicio(f"OSTEOSÍNTESIS DE FÉMUR código {variante}", "CL4506")
        assert r == "OSTEOSÍNTESIS DE FÉMUR", variante
