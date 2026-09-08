"""Las fechas que el hospital declaró salen del XML de la factura.

08-09-2026, con la HUS559324. El sistema avisaba «no hay fechas declaradas
con qué contrastar el RIPS» — y sí las había, en la misma carpeta del
servidor: el `InvoicePeriod` del XML de la factura electrónica y el
`PeriodoAtencion` del resultado del validador del Ministerio.

El caso real de esa factura está reproducido aquí tal cual: RIPS
`2025-02-13 06:55`, XML `2025-02-13`, validador `2025-02-13`, factura
emitida el `2026-09-04`. Las tres fuentes coincidieron y la alerta de
prescripción era correcta.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from app.services.fechas_declaradas_factura import (
    FechasDeclaradas,
    buscar,
    fechas_de_resultado_validador,
    fechas_de_xml,
)

# El XML real de la HUS559324, recortado a lo que importa (sin datos del
# paciente): el documento adjunto que envuelve la factura, con su período.
XML_REAL = """<?xml version="1.0" encoding="utf-8" standalone="no"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
<cbc:ID>587045</cbc:ID><cbc:IssueDate>2026-09-04</cbc:IssueDate>
<cac:Attachment><cac:ExternalReference><cbc:Description><![CDATA[<Invoice>
<cbc:LineCountNumeric>1</cbc:LineCountNumeric>
<cac:InvoicePeriod><cbc:StartDate>2025-02-13</cbc:StartDate>
<cbc:StartTime>06:54:53-05:00</cbc:StartTime><cbc:EndDate>2025-02-13</cbc:EndDate>
<cbc:EndTime>06:55:39-05:00</cbc:EndTime></cac:InvoicePeriod>
<cac:OrderReference><cbc:ID>SIN CONTRATO</cbc:ID></cac:OrderReference>
</Invoice>]]></cbc:Description></cac:ExternalReference></cac:Attachment>
</AttachedDocument>"""

RESULTADO_REAL = {
    "ResultState": True,
    "NumFactura": "HUS559324",
    "CodigoUnicoValidacion": "238dbf2b0ae5",
    "FechaRadicacion": "2026-09-04T19:32:10.974295+00:00",
    "ModalidadPago": "Pago por evento.",
    "PeriodoAtencion": {"FechaInicio": "2025-02-13T00:00:00", "FechaFin": "2025-02-13T00:00:00"},
}


class TestElXmlDeLaFactura:
    def test_saca_el_periodo_de_atencion_del_caso_real(self, tmp_path):
        p = tmp_path / "ad09000060370002600587045.xml"
        p.write_text(XML_REAL, encoding="utf-8")
        f = fechas_de_xml(p)
        assert f.completas
        assert f.fecha_ingreso == datetime(2025, 2, 13)
        assert f.fecha_egreso == datetime(2025, 2, 13)
        assert f.origen == "factura electrónica"
        assert not f.problema

    def test_tambien_lee_el_fv_suelto(self, tmp_path):
        p = tmp_path / "fv09000060370002600587045.xml"
        p.write_text(
            "<Invoice><cac:InvoicePeriod><cbc:StartDate>2026-01-05</cbc:StartDate>"
            "<cbc:EndDate>2026-01-09</cbc:EndDate></cac:InvoicePeriod></Invoice>",
            encoding="utf-8",
        )
        f = fechas_de_xml(p)
        assert f.fecha_ingreso == datetime(2026, 1, 5)
        assert f.fecha_egreso == datetime(2026, 1, 9)

    def test_un_xml_sin_periodo_lo_dice(self, tmp_path):
        p = tmp_path / "fv_sin_periodo.xml"
        p.write_text("<Invoice><cbc:ID>1</cbc:ID></Invoice>", encoding="utf-8")
        f = fechas_de_xml(p)
        assert not f.completas
        assert "InvoicePeriod" in f.problema

    def test_un_archivo_que_no_esta_no_revienta(self, tmp_path):
        assert "no se encontró" in fechas_de_xml(tmp_path / "no_existe.xml").problema

    def test_tolera_el_bom_y_la_codificacion_vieja(self, tmp_path):
        p = tmp_path / "fv_bom.xml"
        p.write_text(XML_REAL, encoding="utf-8-sig")
        assert fechas_de_xml(p).completas
        q = tmp_path / "fv_latin.xml"
        q.write_bytes(XML_REAL.replace("SIN CONTRATO", "ATENCIÓN Ñ").encode("latin-1"))
        assert fechas_de_xml(q).completas


class TestElValidadorDelMinisterio:
    def test_saca_el_periodo_de_atencion(self, tmp_path):
        p = tmp_path / "ResultadosDoker_HUS559324_040926143210979.json"
        p.write_text(json.dumps(RESULTADO_REAL), encoding="utf-8")
        f = fechas_de_resultado_validador(p)
        assert f.fecha_ingreso == datetime(2025, 2, 13)
        assert f.origen == "validador del Ministerio"

    def test_un_json_sin_periodo_lo_dice(self, tmp_path):
        p = tmp_path / "ResultadosMSPS_x.json"
        p.write_text('{"NumFactura": "HUS1"}', encoding="utf-8")
        assert "PeriodoAtencion" in fechas_de_resultado_validador(p).problema

    def test_un_json_roto_no_revienta(self, tmp_path):
        p = tmp_path / "ResultadosMSPS_roto.json"
        p.write_text('{"PeriodoAt', encoding="utf-8")
        assert "JSON" in fechas_de_resultado_validador(p).problema


class TestBuscarEnElServidor:
    def _carpeta(self, tmp_path, periodo="202609", factura="HUS559324"):
        c = tmp_path / periodo / "FACTURAS_SALUD" / factura
        c.mkdir(parents=True, exist_ok=True)
        return c

    def test_encuentra_el_xml_en_la_carpeta_de_la_factura(self, tmp_path):
        c = self._carpeta(tmp_path)
        (c / "ad09000060370002600587045.xml").write_text(XML_REAL, encoding="utf-8")
        f = buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path))
        assert f.completas and f.fecha_egreso == datetime(2025, 2, 13)

    def test_prefiere_el_xml_sobre_el_validador(self, tmp_path):
        c = self._carpeta(tmp_path)
        (c / "fv1.xml").write_text(
            "<Invoice><cac:InvoicePeriod><cbc:StartDate>2025-02-13</cbc:StartDate>"
            "<cbc:EndDate>2025-02-13</cbc:EndDate></cac:InvoicePeriod></Invoice>",
            encoding="utf-8",
        )
        distinto = dict(RESULTADO_REAL)
        distinto["PeriodoAtencion"] = {"FechaInicio": "2020-01-01", "FechaFin": "2020-01-01"}
        (c / "ResultadosMSPS_x.json").write_text(json.dumps(distinto), encoding="utf-8")
        assert buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path)).origen == (
            "factura electrónica"
        )

    def test_cae_al_validador_si_no_hay_xml(self, tmp_path):
        c = self._carpeta(tmp_path)
        (c / "ResultadosDoker_x.json").write_text(json.dumps(RESULTADO_REAL), encoding="utf-8")
        f = buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path))
        assert f.completas and f.origen == "validador del Ministerio"

    def test_tambien_mira_dentro_de_la_subcarpeta_RIPS(self, tmp_path):
        c = self._carpeta(tmp_path) / "RIPS"
        c.mkdir(parents=True)
        (c / "ResultadosMSPS_x.json").write_text(json.dumps(RESULTADO_REAL), encoding="utf-8")
        assert buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path)).completas

    def test_si_no_esta_lo_dice_con_los_periodos(self, tmp_path):
        self._carpeta(tmp_path)
        f = buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path))
        assert not f.completas
        assert "202609" in f.problema

    def test_sin_servidor_configurado_lo_dice(self, monkeypatch):
        monkeypatch.setattr("app.services.rips_localizador._raiz_configurada", lambda: None)
        monkeypatch.delenv("FACTURACION_ELECTRONICA_ROOT", raising=False)
        monkeypatch.delenv("FE_ROOT", raising=False)
        assert "no está configurado" in buscar("HUS1", date(2026, 9, 4)).problema.lower()

    def test_un_pdf_no_se_confunde_con_el_xml(self, tmp_path):
        c = self._carpeta(tmp_path)
        (c / "fv09000060370002600587045.pdf").write_text("no soy xml", encoding="utf-8")
        assert not buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path)).completas


class TestElContrato:
    def test_sin_fechas_no_esta_completo(self):
        assert not FechasDeclaradas().completas
        assert not FechasDeclaradas(fecha_ingreso=datetime(2025, 1, 1)).completas

    def test_el_dict_viaja_como_json(self):
        d = FechasDeclaradas(
            fecha_ingreso=datetime(2025, 2, 13),
            fecha_egreso=datetime(2025, 2, 13),
            origen="factura electrónica",
            archivo="ad1.xml",
        ).a_dict()
        json.dumps(d)
        assert d["fecha_egreso"] == "2025-02-13T00:00:00"
        assert d["completas"] is True

    def test_es_inmutable(self):
        with pytest.raises(Exception):
            FechasDeclaradas().origen = "otro"


class TestElCasoRealCompleto:
    """La HUS559324 de punta a punta: las tres fuentes tienen que coincidir."""

    def test_rips_xml_y_validador_dicen_lo_mismo_y_la_cuenta_esta_prescrita(self, tmp_path):
        from app.services.cotejo_fechas_atencion import cotejar
        from app.services.prescripcion_adres import evaluar
        from app.services.rips_fechas_atencion import fechas_de_datos

        rips = fechas_de_datos(
            {
                "numDocumentoIdObligado": "900006037",
                "numFactura": "HUS559324",
                "usuarios": [
                    {
                        "tipoDocumentoIdentificacion": "CC",
                        "numDocumentoIdentificacion": "1",
                        "codSexo": "M",
                        "servicios": {
                            "procedimientos": [{"fechaInicioAtencion": "2025-02-13 06:55"}]
                        },
                    }
                ],
            }
        )
        assert rips.fecha_egreso == datetime(2025, 2, 13, 6, 55)
        assert rips.tipo_atencion == "AMBULATORIO"

        c = tmp_path / "202609" / "FACTURAS_SALUD" / "HUS559324"
        c.mkdir(parents=True)
        (c / "ad09000060370002600587045.xml").write_text(XML_REAL, encoding="utf-8")
        declaradas = buscar("HUS559324", date(2026, 9, 4), raiz=str(tmp_path))

        # Las dos fuentes coinciden: ningún reparo de fechas.
        hallazgos = cotejar(
            rips,
            ingreso_declarado=declaradas.fecha_ingreso,
            egreso_declarado=declaradas.fecha_egreso,
            fecha_factura=date(2026, 9, 4),
            fecha_recibido=date(2026, 9, 4),
        )
        assert hallazgos == []

        # Y la cuenta llegó pasada de plazo: 18 meses vencieron el 13-08-2026.
        p = evaluar(rips.fecha_egreso, hoy=date(2026, 9, 8))
        assert p.prescrita
        assert p.fecha_corte == date(2026, 8, 13)
        assert p.dias_vencida == 26
