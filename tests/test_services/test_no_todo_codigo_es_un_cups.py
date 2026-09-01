"""Un código interno no es un CUPS (21-08-2026).

Yesid probó dos glosas reales y los dictámenes salieron diciendo:

    «CORRESPONDE A UN DISPOSITIVO MÉDICO CON **CUPS FMQ0952**, ELECTRODO ECG
     ADULTO REF 302A»
    «Servicio objetado: DIPIRONA SODICA 1G/2ML - **CUPS 34363-4**»

`FMQ0952` es un código **interno del hospital** para insumos. `34363-4` es un
**CUM**, el código de un medicamento. Ninguno es un CUPS: los del Ministerio
son seis dígitos, a veces con un sufijo de letra (`890283H`).

POR QUÉ IMPORTA: la EPS cruza los CUPS contra su sistema. Un código que no
existe como CUPS no lo encuentra, y ratifica la glosa completa — así el
argumento jurídico esté impecable.

LO QUE **NO** SE HACE, y es la mitad importante: no se prohíbe nombrar el
código. El hospital SÍ factura con `FMQ0952`, y ponerlo ayuda a que la EPS
ubique el ítem. Lo que está mal es **la etiqueta**: llamarlo CUPS. Por eso el
aviso dice «deje el código y cambie la palabra».
"""

from __future__ import annotations

import pytest

from app.services.citation_verifier import _verificar_cups


def _tipos(texto: str) -> list[str]:
    issues: list[dict] = []
    _verificar_cups(texto, issues)
    return [i["tipo"] for i in issues]


class TestLosCodigosQueNoSonCups:
    @pytest.mark.parametrize(
        "codigo",
        [
            "FMQ0952",  # electrodo ECG — el caso de Yesid
            "FMQ0113",  # catéter intravenoso
            "FMQ0546",  # agujas espinales
            "34363-4",  # dipirona — CUM
            "20010043-24",  # misoprostol — CUM
            "19929516-5",  # acetaminofén — CUM
            "2016DM-0000215-R2",  # registro INVIMA
        ],
    )
    def test_se_avisa_que_no_es_un_cups(self, codigo):
        assert "CODIGO_NO_ES_CUPS" in _tipos(f"SERVICIO FACTURADO CON CUPS {codigo}.")

    def test_el_aviso_dice_que_el_codigo_puede_estar_bien(self):
        """No es «borre el código»: es «cambie la palabra». El hospital factura
        con esos códigos y ponerlos ayuda a la EPS a ubicar el ítem."""
        issues: list[dict] = []
        _verificar_cups("SERVICIO FACTURADO CON CUPS FMQ0952.", issues)
        assert "cambie la palabra" in issues[0]["sugerencia"]
        assert "FMQ0952" in issues[0]["sugerencia"]

    def test_distingue_de_donde_viene_el_codigo(self):
        issues: list[dict] = []
        _verificar_cups("CUPS FMQ0952 Y CUPS 34363-4.", issues)
        detalles = " ".join(i["detalle"] for i in issues)
        assert "institucional" in detalles
        assert "CUM" in detalles


class TestLosCupsRealesNoSeMarcan:
    """La mitad que importa: un aviso equivocado en cada dictamen enseña al
    auditor a ignorar los avisos. Estos son CUPS reales de las facturas del
    HUS, sacados del archivo del 19 de agosto."""

    @pytest.mark.parametrize(
        "codigo",
        [
            "890201",  # consulta de urgencias
            "740001",  # cesárea segmentaria
            "898003",  # estudio anatomopatológico
            "814725",  # condroplastia
            "906340",  # SARS COV 2 antígeno
            "882317",  # ecografía doppler
            "890283H",  # consulta especialista — con sufijo
            "129A02H",  # internación adultos
            "862003B",  # desbridamiento
            "625104PUR",  # fijación testicular
            "061002H",  # paquete ACAF de tiroides
            "869501H1",  # curaciones mediana
            "922443H",  # teleterapia
            "441302H",  # esofagogastroduodenoscopia
        ],
    )
    def test_no_se_marca(self, codigo):
        assert "CODIGO_NO_ES_CUPS" not in _tipos(f"SERVICIO FACTURADO CON CUPS {codigo}.")

    def test_un_anio_no_es_un_codigo(self):
        """«MANUAL TARIFARIO SOAT CUPS 2026» no puede disparar el aviso."""
        assert not _tipos("MANUAL TARIFARIO SOAT CUPS 2026 VIGENTE.")


class TestSigueCazandoElCupsInventado:
    """No se puede perder lo que ya funcionaba: el 20-08 el motor tomó «valor
    glosado 100000» y escribió «CUPS 100000»."""

    @pytest.mark.parametrize("codigo", ["100000", "999999", "123456"])
    def test_un_cups_de_seis_digitos_que_no_existe_sigue_saliendo(self, codigo):
        assert "CUPS_INEXISTENTE" in _tipos(f"SERVICIO FACTURADO CUPS {codigo}.")
