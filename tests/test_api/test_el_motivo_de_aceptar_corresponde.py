"""Cuando el hospital acepta una glosa, el motivo tiene que ser el de ESA glosa.

20-08-2026. Yesid respondió una glosa «FA0102 — se glosa insumo no facturable
dentro de estancias», la aceptó, y el documento que se radica ante la EPS salió
diciendo:

    «ESE HUS ACEPTA GLOSA TOTAL POR VALOR DE $ 10,000 … ESTO CORRESPONDE A UN
     MAYOR VALOR COBRADO SEGÚN CONTRATO S-13-1-03-1-04958 PACTADO ENTRE LAS
     PARTES. SE AJUSTAN LOS VALORES DANDO CUMPLIMIENTO A ESTAS TARIFAS.»

Yesid: «revisar esta respuesta porque sale MVC si estamos hablando de que el
insumo no es facturable?».

Tenía razón. «Mayor valor cobrado» es un motivo de TARIFA. Esa glosa no era de
tarifa: era de facturación — un insumo que no se cobra aparte porque ya va
dentro de la estancia. El texto estaba escrito a mano, IGUAL PARA TODAS LAS
CAUSALES, así que en cualquier glosa que no fuera TA el hospital estaba
radicando un motivo que no corresponde. Y citaba un número de contrato que ahí
no venía al caso.

De paso: «$ 10,000» con coma. En Colombia la coma es el separador decimal —
«10,000» se lee como diez.
"""

from __future__ import annotations

import re

import pytest

from app.api.routers.analizar import (
    _construir_dictamen_aceptacion,
    _motivo_de_aceptacion,
    _pesos_col,
)

CONTRATO = "CONTRATO S-13-1-03-1-04958"


def _texto(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip().upper()


class TestElCasoDeYesid:
    """FA0102 — insumo no facturable dentro de estancias, aceptada al 100%."""

    def _dictamen(self) -> str:
        return _texto(
            _construir_dictamen_aceptacion(
                eps="FAMISANAR EPS",
                codigo_glosa="FA0102",
                val_obj=10000.0,
                val_ac=10000.0,
                estado="ACEPTADA",
                cod_resp="RE9702",
                desc_resp="GLOSA ACEPTADA AL 100%",
                tabla_excel="fa0102 - se glosa insumo no faturable dentro de estancias",
                contexto_pdf="",
            )
        )

    def test_ya_no_dice_mayor_valor_cobrado(self):
        assert "MAYOR VALOR COBRADO" not in self._dictamen()

    def test_ya_no_cita_un_contrato_que_no_viene_al_caso(self):
        assert "S-13-1-03-1-04958" not in self._dictamen()

    def test_dice_el_motivo_que_si_corresponde(self):
        assert "OBSERVACIÓN DE FACTURACIÓN" in self._dictamen()

    def test_la_plata_va_en_formato_colombiano(self):
        d = self._dictamen()
        assert "$10.000" in d
        assert "10,000" not in d


class TestCadaCausalDiceLoSuyo:
    @pytest.mark.parametrize(
        "codigo,debe_decir",
        [
            ("TA0201", "MAYOR VALOR COBRADO"),
            ("FA0102", "FACTURACIÓN"),
            ("SO0201", "SOPORTE"),
            ("AU0301", "AUTORIZACIÓN"),
            ("CO0601", "NO CUBIERTO"),
            ("CL0801", "PERTINENCIA"),
        ],
    )
    def test_el_motivo_corresponde_a_la_familia(self, codigo, debe_decir):
        assert debe_decir in _motivo_de_aceptacion(codigo, CONTRATO).upper()

    def test_solo_la_de_tarifa_cita_el_contrato(self):
        """Citar el contrato en una glosa de soportes es relleno que delata."""
        assert CONTRATO in _motivo_de_aceptacion("TA0201", CONTRATO)
        for codigo in ("FA0102", "SO0201", "CO0601", "AU0301", "CL0801"):
            assert CONTRATO not in _motivo_de_aceptacion(codigo, CONTRATO), codigo


class TestCuandoNoSeSabe:
    """Sin causal reconocida NO se inventa un motivo: se acepta y ya."""

    @pytest.mark.parametrize("codigo", ["ZZ9999", "", None, "   "])
    def test_no_inventa_una_razon(self, codigo):
        m = _motivo_de_aceptacion(codigo, CONTRATO).upper()
        assert "AJUSTE CORRESPONDIENTE" in m
        assert "MAYOR VALOR" not in m
        assert CONTRATO not in m


class TestLaPlata:
    @pytest.mark.parametrize(
        "valor,escrito",
        [(10000, "$10.000"), (213752, "$213.752"), (5724661, "$5.724.661"), (0, "$0")],
    )
    def test_punto_de_miles_como_en_colombia(self, valor, escrito):
        assert _pesos_col(valor) == escrito

    def test_nunca_deja_una_coma(self):
        for v in (1000, 1_000_000, 999_999_999):
            assert "," not in _pesos_col(v)

    def test_un_valor_roto_no_revienta(self):
        assert _pesos_col(None) == "$0"


class TestAceptacionParcial:
    def _parcial(self) -> str:
        return _texto(
            _construir_dictamen_aceptacion(
                eps="FAMISANAR EPS",
                codigo_glosa="SO0201",
                val_obj=100000.0,
                val_ac=40000.0,
                estado="PARCIALMENTE_ACEPTADA",
                cod_resp="RE9801",
                desc_resp="GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE",
                tabla_excel="SO0201 falta soporte",
                contexto_pdf="",
            )
        )

    def test_el_motivo_tambien_corresponde(self):
        d = self._parcial()
        assert "SOPORTE" in d
        assert "MAYOR VALOR COBRADO" not in d

    def test_las_dos_cifras_en_formato_colombiano(self):
        d = self._parcial()
        assert "$40.000" in d
        assert "$60.000" in d, "el valor no aceptado también se radica"

    def test_no_afirma_que_el_resto_es_el_valor_pactado(self):
        """Decía «corresponde al valor pactado» en TODA glosa parcial, aunque
        no fuera de tarifa y aunque no hubiera contrato que lo respaldara."""
        assert "VALOR PACTADO ENTRE LAS PARTES" not in self._parcial()
