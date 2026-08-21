"""La plata se escribe con punto de miles (21-08-2026).

Yesid vio dos cifras con **coma** en pantalla:

    Panel de tarifa:   «Tarifa pactada en contrato   $2,072,200»
                       «El hospital facturó $0, MENOR al pactado ($2,072,200)»
    Aceptación parcial: «Valor en disputa   $ 2,288,600»

En Colombia la coma es el separador **decimal**: `$2,072,200` se lee como dos
con setenta y dos milésimas. Una cifra mal escrita en una respuesta de glosa es
una discusión que nadie quiere tener con la EPS.

Y la otra mitad del mismo problema: el dictamen declaraba **«VALOR OBJETADO
$ 0.00»** aunque el texto de la glosa sí traía el valor. Eso no es formato: es
una cifra falsa en un documento que se radica.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.routers.analizar import _pesos_col
from app.services.glosa_service import GlosaService
from app.services.tarifa_lookup_service import _pesos as _pesos_tarifa
from app.utils.parsers_glosa import _pesos as _pesos_parsers


class TestLosTresFormateadores:
    @pytest.mark.parametrize("fn", [_pesos_col, _pesos_tarifa, _pesos_parsers])
    def test_las_cifras_exactas_que_vio_yesid(self, fn):
        assert fn(2072200) == "$2.072.200"
        assert fn(2288600) == "$2.288.600"

    @pytest.mark.parametrize("fn", [_pesos_col, _pesos_tarifa, _pesos_parsers])
    def test_nunca_una_coma(self, fn):
        for v in (1000, 999999, 1234567, 83800, 120000):
            assert "," not in fn(v), f"{fn.__module__} escribió coma en {v}"

    @pytest.mark.parametrize("fn", [_pesos_col, _pesos_tarifa, _pesos_parsers])
    def test_cero_y_nada_no_revientan(self, fn):
        assert fn(0) == "$0"
        assert fn(None) == "$0"


class TestNoQuedanComasEnLoQueSeVE:
    """Barrido: ningún sitio que produzca plata visible puede volver al formato
    gringo."""

    @pytest.mark.parametrize(
        "archivo",
        [
            "app/services/tarifa_lookup_service.py",
            "app/utils/parsers_glosa.py",
        ],
    )
    def test_no_hay_formato_de_miles_gringo(self, archivo):
        texto = (Path(__file__).resolve().parents[2] / archivo).read_text(encoding="utf-8")
        sobras = re.findall(r"\$\{[^{}]+:,\.0f\}", texto)
        assert not sobras, f"volvió el formato con coma en {archivo}: {sobras[:3]}"

    def test_el_valor_en_disputa_usa_el_helper(self):
        texto = (Path(__file__).resolve().parents[2] / "app/api/routers/analizar.py").read_text(
            encoding="utf-8"
        )
        i = texto.index("Valor en disputa")
        trozo = texto[i : i + 700]
        assert "_pesos_col(val_en_disputa)" in trozo
        assert ":,.0f}" not in trozo


class TestElValorSeLeeCuandoEsta:
    """El «$ 0.00» que declaraba cero pesos objetados ante la EPS."""

    @pytest.fixture()
    def svc(self):
        return GlosaService.__new__(GlosaService)

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("CL0801 - 898201 ESTUDIO DE COLORACION - valor 279900", "279900"),
            ("TA5801 - 740001 CESAREA SEGMENTARIA - valor 1980300", "1980300"),
            ("AU5801 - no se aporta autorizacion - valor glosado 2788600", "2788600"),
            ("FA2006 - 34363-4 DIPIRONA SODICA - valor 30", "30"),
            ("TA0701 - 19929516-5 ACETAMINOFEN JARABE - valor 200", "200"),
        ],
    )
    def test_los_textos_reales_de_yesid(self, svc, texto, esperado):
        r = svc._extraer_valor(texto)
        assert esperado in r
        assert "0.00" not in r

    def test_lo_que_ya_funcionaba_no_cambia(self, svc):
        assert "150.000" in svc._extraer_valor("por valor de $150.000")
        assert "1.084.488" in svc._extraer_valor("$ 1.084.488")
        assert "120.000" in svc._extraer_valor("120 mil pesos")

    @pytest.mark.parametrize(
        "texto",
        [
            "glosa aceptada al valor 100%",  # un porcentaje no es plata
            "se detectaron valor 2 conceptos distintos",  # un dígito suelto no basta
            "sin ninguna cifra en el texto",
            "",
        ],
    )
    def test_lo_que_no_es_plata_sigue_dando_cero(self, svc, texto):
        assert svc._extraer_valor(texto) == "$ 0.00"
