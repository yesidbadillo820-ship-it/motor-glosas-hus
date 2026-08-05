"""Un pedazo del número de contrato no es un CUPS.

OT-006 · 05-08-2026. Prueba real en el motor del hospital, glosa FA0101 de
AURORA:

    "Se glosa el procedimiento por cuanto el valor facturado supera la
     tarifa pactada en el Contrato S-13-1-03-1-04958, cláusula 7.4..."

La glosa no traía ningún CUPS. El dictamen salió con "CUPS 04958": la cola
del número de contrato que citaba la propia EPS. La ranura del CUPS ya
descartaba fechas, años, montos y números de factura; faltaba el pedazo de
un código compuesto por guiones o barras.
"""

from __future__ import annotations

from app.utils.parsers_glosa import _extraer_cups_servicio

GLOSA_AURORA = (
    "FA0101 - Se glosa el procedimiento por cuanto el valor facturado supera la "
    "tarifa pactada en el Contrato S-13-1-03-1-04958, cláusula 7.4, que establece "
    "como tarifa máxima SOAT menos el 12%."
)


class TestElCasoReal:
    def test_no_saca_cups_del_numero_de_contrato(self):
        cups, _ = _extraer_cups_servicio(GLOSA_AURORA)
        assert cups == "", f"se coló «{cups}» desde el número de contrato"

    def test_prefiere_quedarse_sin_cups_que_inventarlo(self):
        """Con el CUPS vacío el servicio queda «NO IDENTIFICADO» y el prompt
        enciende el aviso que ya existe para ese caso. Mejor eso que un
        procedimiento falso en un documento que se radica."""
        cups, servicio = _extraer_cups_servicio(GLOSA_AURORA)
        assert (cups, servicio) == ("", "")


class TestOtrosCodigosCompuestos:
    def test_contrato_con_barra(self):
        t = "TA0801 — diferencia de tarifa según el contrato 440-DIGSA/DMBUG-2025."
        assert _extraer_cups_servicio(t)[0] == ""

    def test_contrato_coosalud(self):
        t = "AU0203 — el RIPS no coincide. Contrato 68001C00060340-24 vigente."
        cups = _extraer_cups_servicio(t)[0]
        assert cups in ("", "68001C00060340-24"), f"salió un fragmento: {cups}"

    def test_acta_de_conciliacion(self):
        t = "SO0201 — falta soporte según acta GI-33-5251-2026 de la mesa."
        assert _extraer_cups_servicio(t)[0] == ""


class TestLosCupsDeVerdadSiguenSaliendo:
    def test_cups_suelto_en_el_texto(self):
        t = "AU0401 - Se glosa por cuanto el procedimiento 895201 no corresponde."
        assert _extraer_cups_servicio(t)[0] == "895201"

    def test_cups_entre_guiones_con_descripcion(self):
        t = "FA0202 - 890602 - CONSULTA DE URGENCIAS por valor de $120.000"
        cups, servicio = _extraer_cups_servicio(t)
        assert cups == "890602"
        assert "CONSULTA DE URGENCIAS" in servicio

    def test_cups_con_sufijo_del_hus_conviviendo_con_un_contrato(self):
        """El token COMPLETO puede ser CUPS; lo que se descarta es el
        fragmento de otro código."""
        t = "TA0801 sobre el contrato 440-DIGSA/DMBUG-2025 y el CUPS 372301H"
        assert _extraer_cups_servicio(t)[0] == "372301H"

    def test_sin_texto(self):
        assert _extraer_cups_servicio("") == ("", "")
