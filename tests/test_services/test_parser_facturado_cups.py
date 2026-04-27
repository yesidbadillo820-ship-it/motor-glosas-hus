"""Tests del parser de valor facturado por línea de CUPS.

Bug real reportado el 27-abr-2026: en facturas multi-CUPS, el parser
tomaba el TOTAL ORDEN DE SERVICIO y se lo pasaba al LLM como
"valor facturado del CUPS", llevando a dictámenes que aceptaban
montos de OTROS servicios legítimos como excedente.
"""
from __future__ import annotations

from app.utils.parsers_glosa import (
    _extraer_valores_glosa,
    _facturado_linea_cups,
)


# Factura HUS multi-CUPS (caso real HUS491868)
FACTURA_MULTI = """
HOSPITAL UNIVERSITARIO DE SANTANDER
FACTURA ELECTRONICA DE VENTA HUS0000491868
CONSULTAS MEDICAS
0023456  CONSULTA DE CONTROL ESPECIALIZADA
1,00 $ 50.000,00 $ 0,00 $ 50.000,00
LABORATORIOS
902210  HEMOGRAMA IV (HEMOGLOBINA HEMATOCRITO) AUTOMATIZADO
1,00  $ 41.151,00  $ 0,00  $ 41.151,00
FMQ0178-3  TRANSAMINASA GOT
0,00 $ 1.000,00 $ 0,00 $ 0,00
VALOR SUBTOTAL DE SERVICIOS PRESTADOS    $ 488.497,00
VALOR TOTAL ORDEN DE SERVICIO            $ 488.497,00
"""

# Factura single-CUPS (caso TA0201 HUS493179)
FACTURA_SIMPLE = """
39147B-18  CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA
1,00  $ 247.663,00  $ 0,00  $ 247.663,00
VALOR TOTAL ORDEN DE SERVICIO    $ 247.663,00
"""


class TestFacturadoLineaCups:
    def test_extrae_linea_cups_multi(self):
        # CUPS específico → su valor de línea, no el total.
        v = _facturado_linea_cups(FACTURA_MULTI.upper(), "902210")
        assert v == 41151.0

    def test_extrae_linea_cups_single(self):
        v = _facturado_linea_cups(FACTURA_SIMPLE.upper(), "39147B-18")
        assert v == 247663.0

    def test_cups_no_aparece_devuelve_cero(self):
        v = _facturado_linea_cups(FACTURA_MULTI.upper(), "999999")
        assert v == 0.0

    def test_texto_o_cups_vacio(self):
        assert _facturado_linea_cups("", "902210") == 0.0
        assert _facturado_linea_cups(FACTURA_MULTI, "") == 0.0


class TestExtraerValoresGlosa:
    def test_sin_cups_toma_total_o_subtotal(self):
        # Para facturas single-CUPS está bien usar el total.
        v = _extraer_valores_glosa(FACTURA_SIMPLE)
        assert v["facturado"] == 247663.0

    def test_con_cups_toma_linea(self):
        # En multi-CUPS, debemos tomar la línea del CUPS pedido.
        v = _extraer_valores_glosa(FACTURA_MULTI, cups="902210")
        assert v["facturado"] == 41151.0

    def test_con_cups_inexistente_devuelve_cero(self):
        # Si conocemos el CUPS y NO lo encontramos en el texto, NO
        # caemos al TOTAL — eso causaría que la IA tome el total de
        # toda la factura como si fuera el valor del CUPS específico
        # y aceptara montos que no debía. Preferimos 0 (incertidumbre)
        # a un valor erróneo.
        v = _extraer_valores_glosa(FACTURA_MULTI, cups="ZZZ")
        assert v["facturado"] == 0.0

    def test_modo_estricto_evita_contaminacion_multi_cups(self):
        """Caso real producción 27-abr-2026: lote 9 conceptos, parser
        no debe agarrar valor de OTRO concepto ni el total como
        valor de la línea actual."""
        texto_lote = "TA2301 - CUPS 938303 - Valor objetado: $16.656"
        # Sin contexto PDF de la línea 938303 → 0 facturado, no
        # invención.
        v = _extraer_valores_glosa(texto_lote, cups="938303")
        assert v["facturado"] == 0.0
