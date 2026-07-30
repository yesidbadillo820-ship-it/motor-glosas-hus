"""Ronda 30 — regresiones de parsing de dinero y extractores.

Bugs confirmados por la auditoría ultracode:
  #21 multiplicador verbal aplicado a cifra ya completa.
  #22 parse_valor_cop sobre el texto completo → cifra 10^27.
  #23 formato US "1,234,567.89" inflado ×100.
  #24 número de factura capturado como valor facturado.
  #25 puntuación pegada al monto rompía el parseo.
  #26 "RADIOGRAFIA" capturada como número de radicado.
  #28 valor objetado tomado como CUPS.
  #29 comparadores "< 5%" borrados del dictamen como si fueran tags.
  #30 signo negativo inconsistente.
"""

from __future__ import annotations

import pytest

from app.utils.moneda import parse_valor_cop


# ── moneda.py ────────────────────────────────────────────────────────────


class TestParseValorRonda30:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("$5.000.000 (CINCO MILLONES DE PESOS M/CTE)", 5_000_000),  # #21
            ("850 millones", 850_000_000),  # no romper el caso legítimo
            ("1,234,567.89", 1_234_567.89),  # #23 formato US
            ("1,234.56", 1_234.56),  # #23
            ("1.234,56", 1_234.56),  # colombiano equivalente
            ("-1.500", -1500.0),  # #30
            ("-1.500,00", -1500.0),  # #30
        ],
    )
    def test_valores(self, texto, esperado):
        assert abs(parse_valor_cop(texto) - esperado) < 0.01

    def test_multiplicador_no_dispara_sin_digito_adyacente(self):
        # "CINCO MILLONES" (letras antes de la palabra escala) no multiplica.
        assert parse_valor_cop("$5.000.000 (CINCO MILLONES)") == 5_000_000


# ── parsers_glosa.py ─────────────────────────────────────────────────────


class TestExtraerValoresRonda30:
    def test_numero_factura_no_es_valor_facturado(self):  # #24
        from app.utils.parsers_glosa import _extraer_valores_glosa

        r = _extraer_valores_glosa(
            "SE GLOSA LA FACTURA 90228637 POR FALTA DE EPICRISIS. VALOR OBJETADO $149.000"
        )
        assert r["facturado"] == 0.0
        assert r["objetado"] == 149000.0

    def test_puntuacion_pegada_al_monto(self):  # #25
        from app.utils.parsers_glosa import _extraer_valores_glosa

        r = _extraer_valores_glosa(
            "VALOR FACTURADO POR $114.900,00, VALOR OBJETADO $14.900,00, "
            "VALOR A RECONOCER $100.000,00."
        )
        assert r["facturado"] == 114900.0
        assert r["objetado"] == 14900.0

    def test_valor_no_se_confunde_con_cups(self):  # #28
        from app.utils.parsers_glosa import _extraer_cups_servicio

        cups, _ = _extraer_cups_servicio(
            "SO0101 - FALTA SOPORTE - CONSULTA URGENCIAS - 149000 - GLOSA TOTAL",
            montos_excluir=[149000.0, 0.0],
        )
        assert cups != "149000"


# ── extractor_factura.py ─────────────────────────────────────────────────


class TestExtractorFacturaRonda30:
    def test_radiografia_no_es_radicado(self):  # #26
        from app.services.extractor_factura import extraer_de_texto

        r = extraer_de_texto(
            "RADIOGRAFIA DE TORAX. FACTURA HUS0000492150. RADICADO 202600123 DEL 2026"
        )
        assert r["numero_radicado"] == "202600123"
        assert r["numero_factura"] == "HUS0000492150"


# ── html_a_texto.py ──────────────────────────────────────────────────────


class TestHtmlATextoRonda30:
    def test_comparadores_no_se_borran(self):  # #29
        from app.utils.html_a_texto import dictamen_a_texto_plano

        out = dictamen_a_texto_plano(
            "El valor objetado es < 5% del total y la estancia fue > 20 dias. <b>SE RATIFICA</b>"
        )
        assert "< 5%" in out
        assert "> 20 dias" in out
        assert "SE RATIFICA" in out
        assert "<b>" not in out
