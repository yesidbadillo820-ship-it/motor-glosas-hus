"""Cuando las cifras vienen con nombre, mandan los nombres.

09-09-2026, prueba real del auditor. Corrió esta glosa:

    «TA0201 $185.000 CONSULTA DE PRIMERA VEZ POR MEDICINA ESPECIALIZADA
     890201 - VALOR FACTURADO $185.000 SUPERIOR AL PACTADO $157.250 SEGUN
     CONTRATO SOAT -15%. SE OBJETA LA DIFERENCIA.»

y el motor leyó **$157.250 como el valor facturado**. Es el PACTADO: justo
lo contrario.

QUÉ COSTÓ. Con esa cifra al revés, el motor comparó contra la tarifa real
del contrato ($51.900) y recomendó **aceptar $105.350**. La cuenta buena es
$185.000 − $51.900 = **$133.100**. El auditor le dio a «Aplicar
recomendación» — o sea que en una glosa de verdad el hospital habría
regalado plata, y calculada sobre un número leído al revés.

POR QUÉ PASABA, Y NO ERA UN DESCUIDO. `_facturado_linea_cups` está hecha
para leer FILAS DE FACTURA, donde los montos son columnas mudas
(«1,00 $247.663,00 $0,00 $247.663,00») y el último es el valor de la línea.
Esa regla es correcta ahí, y nació de un incidente real del 27-abr-2026: en
una factura de nueve conceptos el motor le pasaba a la IA el TOTAL de la
factura como valor de cada línea.

Lo que no se había visto es que la misma función recibe también el TEXTO de
la glosa, donde la entidad le pone nombre a cada cifra. Ahí «el último
monto» no es lo facturado: es lo que la entidad escribió de último.

LA REGLA QUE QUEDA. Si las cifras del fragmento vienen con nombre —pactado,
contratado, reconocido, objetado, glosado, diferencia—, no es una fila de
factura: se leen las etiquetas. Si son columnas mudas, sigue mandando la
regla de la línea del CUPS, intacta.
"""

from __future__ import annotations

import pytest

from app.utils.parsers_glosa import (
    _extraer_valores_glosa,
    _facturado_linea_cups,
    _las_cifras_vienen_con_nombre,
)

# El caso exacto de la prueba del auditor.
CASO_DEL_AUDITOR = (
    "TA0201 $185.000 CONSULTA DE PRIMERA VEZ POR MEDICINA ESPECIALIZADA 890201 - "
    "VALOR FACTURADO $185.000 SUPERIOR AL PACTADO $157.250 SEGUN CONTRATO "
    "SOAT -15%. SE OBJETA LA DIFERENCIA."
)

# Una fila de factura de verdad: columnas mudas, sin etiquetas.
FILA_DE_FACTURA = """
902210  HEMOGRAMA IV (HEMOGLOBINA HEMATOCRITO) AUTOMATIZADO
1,00  $ 41.151,00  $ 0,00  $ 41.151,00
"""


class TestElCasoQueLoDestapo:
    def test_lee_lo_facturado_y_no_lo_pactado(self):
        v = _extraer_valores_glosa(CASO_DEL_AUDITOR, cups="890201")
        assert v["facturado"] == 185000.0, (
            "Volvió a leer el PACTADO como si fuera el facturado. Con esa "
            "cifra el motor recomienda aceptar una suma calculada al revés."
        )

    def test_el_pactado_no_se_cuela_por_ningun_lado(self):
        v = _extraer_valores_glosa(CASO_DEL_AUDITOR, cups="890201")
        assert 157250.0 not in v.values()

    def test_da_igual_con_o_sin_cups(self):
        """El defecto solo salía cuando se conocía el CUPS: los dos caminos
        tienen que leer lo mismo."""
        con = _extraer_valores_glosa(CASO_DEL_AUDITOR, cups="890201")["facturado"]
        sin = _extraer_valores_glosa(CASO_DEL_AUDITOR)["facturado"]
        assert con == sin == 185000.0


class TestOtrasFormasDeEscribirLoMismo:
    """La entidad no siempre escribe igual. Todas estas son la misma trampa."""

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("CUPS 890201 VALOR FACTURADO $185.000 VS TARIFA PACTADA $157.250", 185000.0),
            ("890201 FACTURADO $500.000 - RECONOCIDO $300.000", 500000.0),
            ("890201 SE FACTURO $90.000 Y LA TARIFA CONTRATADA ES $70.000", 90000.0),
            ("890201 VALOR FACTURADO $250.000, SE OBJETA $50.000 DE DIFERENCIA", 250000.0),
        ],
    )
    def test_siempre_gana_la_etiqueta(self, texto, esperado):
        assert _extraer_valores_glosa(texto, cups="890201")["facturado"] == esperado


class TestLaReglaDeLaFacturaSigueIntacta:
    """El incidente del 27-abr-2026 no puede volver: en una factura de varios
    conceptos, el motor no puede tomar el total como valor de cada línea."""

    def test_una_fila_de_factura_se_sigue_leyendo_por_posicion(self):
        assert _facturado_linea_cups(FILA_DE_FACTURA.upper(), "902210") == 41151.0

    def test_con_cups_ausente_sigue_devolviendo_cero(self):
        """Preferir la incertidumbre a un valor de otra fila."""
        assert _extraer_valores_glosa(FILA_DE_FACTURA, cups="ZZZ")["facturado"] == 0.0

    def test_una_glosa_con_una_sola_cifra_no_inventa_un_facturado(self):
        """«Valor objetado: $16.656» no dice cuánto se facturó, y el motor no
        puede suponerlo."""
        texto = "TA2301 - CUPS 938303 - Valor objetado: $16.656"
        assert _extraer_valores_glosa(texto, cups="938303")["facturado"] == 0.0


class TestElDetectorDeEtiquetas:
    @pytest.mark.parametrize(
        "prosa",
        [
            "VALOR FACTURADO $185.000 SUPERIOR AL PACTADO $157.250",
            "FACTURADO $1.000 Y RECONOCIDO $800",
            "TARIFA CONTRATADA $500",
            "SE OBJETA UNA DIFERENCIA DE $200",
            "VALOR GLOSADO $300",
            "LA IPS ACEPTA $100",
        ],
    )
    def test_reconoce_la_prosa_de_una_glosa(self, prosa):
        assert _las_cifras_vienen_con_nombre(prosa), prosa

    @pytest.mark.parametrize(
        "fila",
        [
            "1,00  $ 41.151,00  $ 0,00  $ 41.151,00",
            "2,00 $ 8.500,00 $ 0,00 $ 25.500,00",
            "CONSULTA DE CONTROL ESPECIALIZADA 1,00 $ 50.000,00 $ 50.000,00",
        ],
    )
    def test_no_confunde_una_fila_de_factura_con_prosa(self, fila):
        assert not _las_cifras_vienen_con_nombre(fila), (
            f"Marcó como prosa una fila de factura: {fila}. Eso apagaría la "
            "regla que evita la contaminación entre líneas."
        )

    def test_el_vacio_no_es_prosa(self):
        assert not _las_cifras_vienen_con_nombre("")
        assert not _las_cifras_vienen_con_nombre(None)
