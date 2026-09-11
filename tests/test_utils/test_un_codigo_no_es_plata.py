"""Un código de medicamento se leía como el valor de la factura.

10-09-2026. Caso real de Yesid, factura HUS0000541440. La objeción del
Dispensario decía:

    «...presentan diferencias con las cantidades que fueron FACTURADAS
     224249-2 IOBITRIDOL 300MG/50ML (XENETIX)...»

El patrón que busca «FACTURADAS <número>» se saltó el fin de renglón y tomó
«224249» —el CÓDIGO del medicamento— como el valor facturado. El dictamen
salió con un recuadro rojo diciéndole al auditor:

    «La entidad objeta $55.985.100 sobre una factura de $224.249.
     No se puede glosar un valor que nunca se facturó.»

La factura valía **$126.565.918**.

Lo peligroso no es el número mal leído: es que ese recuadro le dice al
auditor que tiene el caso ganado sin discutir el fondo. Si lo radica, la
entidad abre la factura, ve los 126 millones y ya no le cree nada más del
escrito — que es exactamente el flanco que el propio Quality Gate enumera:
«el documento se contradice solo → tumbo sin entrar en el fondo».
"""

from __future__ import annotations

import pytest

from app.utils.parsers_glosa import _extraer_valores_glosa

# El texto real, tal como lo mandó el Dispensario.
OBJECION_REAL = """FA0701 - Los cargos por Medicamentos o APME que vienen relacionados en los
soportes de cobro, presentan diferencias con las cantidades que fueron facturadas
224249-2 IOBITRIDOL 300MG/50ML (XENETIX) (EQUIVALENTE A 30%P/V DE YODO)
VALOR OBJETADO: $103.000,00
Observaciones: SE OBJETA MEDIO DE CONTRASTE UTILIZADO SEGUN NOTA OPERATORIA
SE UTILIZA 40CC LA HOJA DE GASTOS REGISTRA FRASCO DE 100 ML 50 ML POR LO TANTO
NO SE RECONOCE COBRO DE 4 UNIDADES.
TOTAL OBJETADO: $55.985.100,00"""


class TestElCasoQueLoDestapo:
    def test_el_codigo_del_medicamento_no_se_lee_como_la_factura(self):
        vals = _extraer_valores_glosa(OBJECION_REAL)
        assert vals["facturado"] != 224249.0, (
            "«224249-2» es el código del IOBITRIDOL, no el valor de la factura."
        )

    def test_mejor_cero_que_un_numero_inventado(self):
        """Sin dato es honesto; un dato falso arma un recuadro que miente."""
        vals = _extraer_valores_glosa(OBJECION_REAL)
        assert vals["facturado"] == 0.0

    def test_lo_que_si_estaba_bien_se_sigue_leyendo(self):
        vals = _extraer_valores_glosa(OBJECION_REAL)
        assert vals["objetado"] == 103000.0


class TestNingunCodigoPasaPorPlata:
    @pytest.mark.parametrize(
        "texto,por_que",
        [
            ("QUE FUERON FACTURADAS\n224249-2 IOBITRIDOL", "código con guion y dígito detrás"),
            ("QUE FUERON FACTURADAS\n20013906-1 MORFINA", "idem, otro medicamento de la factura"),
            ("QUE FUERON FACTURADAS\n19936296-11 ACIDO ACETILSALICILICO", "sufijo de dos dígitos"),
            ("SE FACTURARON\nFMQ6476 COIL MODELO TARGET", "código de material, letras delante"),
            ("FACTURADO\nHUS0000541440", "número de factura, letras delante"),
        ],
    )
    def test_no_lo_toma_como_valor(self, texto, por_que):
        vals = _extraer_valores_glosa(texto)
        assert vals["facturado"] == 0.0, f"tomó un {por_que} como plata"


class TestLaPlataDeVerdadSigueLlegando:
    """Si esta clase se cae, el arreglo se pasó de estricto."""

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("VALOR FACTURADO $185.000 SUPERIOR AL PACTADO $157.250", 185000.0),
            ("SE FACTURÓ $90.000 Y SE RECONOCIÓ $70.000", 90000.0),
            ("VALOR TOTAL ORDEN DE SERVICIO $ 126.565.918,00", 126565918.0),
            ("FACTURADO POR IPS $ 206.400", 206400.0),
            ("VALOR SUBTOTAL DE SERVICIOS PRESTADOS $126.565.918", 126565918.0),
        ],
    )
    def test_se_lee_igual_que_antes(self, texto, esperado):
        assert _extraer_valores_glosa(texto)["facturado"] == esperado

    def test_el_valor_objetado_y_el_reconocido_tampoco_se_pierden(self):
        vals = _extraer_valores_glosa(
            "SE FACTURÓ $114.900, SE RECONOCIÓ SOLO $90.000, OBJETÁNDOSE $24.900"
        )
        assert vals["facturado"] == 114900.0
        assert vals["reconocido"] == 90000.0
        assert vals["objetado"] == 24900.0
