"""Pruebas de tools/clasificar_regimen_coosalud.py.

Arman un share falso con la estructura real
(<share>/AAAAMM/FACTURAS_SALUD/<factura>/ con XML DIAN + RIPS) y verifican:
regimen por tipoUsuario del RIPS JSON y por el US de los RIPS TXT viejos,
fechas RIPS vs fechas del XML (Interoperabilidad e InvoicePeriod), la copia
de carpetas por regimen y el Excel de auditoria.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import clasificar_regimen_coosalud as cr  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

XML_SUBSIDIADO = """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cac:Attachment><cac:ExternalReference><cbc:Description><![CDATA[
    <Invoice>
      <cbc:ID>HUS349680</cbc:ID>
      <cbc:IssueDate>2026-05-06</cbc:IssueDate>
      <cac:InvoicePeriod>
        <cbc:StartDate>2026-05-01</cbc:StartDate>
        <cbc:EndDate>2026-05-05</cbc:EndDate>
      </cac:InvoicePeriod>
    </Invoice>
  ]]></cbc:Description></cac:ExternalReference></cac:Attachment>
</AttachedDocument>
"""

XML_CONTRIBUTIVO = """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument>
  <cbc:Description><![CDATA[
    <Invoice>
      <cbc:ID>HUS352629</cbc:ID>
      <CustomTagGeneral><Interoperabilidad><Collection>
        <AdditionalInformation>
          <Name>FECHA_INICIO_ATENCION</Name>
          <Value schemeID="1">2026-06-02</Value>
        </AdditionalInformation>
        <AdditionalInformation>
          <Name>FECHA_FINAL_ATENCION</Name>
          <Value schemeID="1">2026-06-04</Value>
        </AdditionalInformation>
      </Collection></Interoperabilidad></CustomTagGeneral>
    </Invoice>
  ]]></cbc:Description>
</AttachedDocument>
"""

RIPS_JSON_SUBSIDIADO = {
    "numFactura": "HUS349680",
    "usuarios": [
        {
            "tipoUsuario": "04",
            "servicios": {
                "consultas": [{"fechaInicioAtencion": "2026-05-01 08:00"}],
                "hospitalizacion": [
                    {"fechaInicioAtencion": "2026-05-01 09:30", "fechaEgreso": "2026-05-05 14:00"}
                ],
            },
        }
    ],
}

CUV_JSON = {"ResultState": True, "CodigoUnicoValidacion": "abc123"}


def _armar_share(tmp_path: Path) -> Path:
    share = tmp_path / "share"

    # Factura 1: subsidiado, RIPS JSON, fechas iguales a la factura → alerta NO.
    c1 = share / "202605" / "FACTURAS_SALUD" / "HUS349680"
    (c1 / "RIPS").mkdir(parents=True)
    (c1 / "ad090056037001.xml").write_text(XML_SUBSIDIADO, encoding="utf-8")
    (c1 / "RIPS" / "HUS349680.json").write_text(json.dumps(RIPS_JSON_SUBSIDIADO), encoding="utf-8")
    (c1 / "RIPS" / "ResultadosDoker_HUS349680.json").write_text(
        json.dumps(CUV_JSON), encoding="utf-8"
    )
    (c1 / "soporte_HAM.pdf").write_bytes(b"%PDF-1.4 fake")

    # Factura 2: contributivo por US de RIPS TXT viejo; solo consultas (egreso
    # derivado) y fechas distintas a las del XML → alerta SI.
    c2 = share / "202606" / "FACTURAS_SALUD" / "HUS352629"
    (c2 / "RIPS").mkdir(parents=True)
    (c2 / "ad090056037002.xml").write_text(XML_CONTRIBUTIVO, encoding="utf-8")
    (c2 / "RIPS" / "US0000001.txt").write_text(
        "CC,123456,EPS047,1,PEREZ,GOMEZ\n", encoding="latin-1"
    )
    (c2 / "RIPS" / "AC0000001.txt").write_text(
        "HUS352629,900006037,CC,123456,03/06/2026,890201\n", encoding="latin-1"
    )
    return share


def _armar_excel(tmp_path: Path) -> Path:
    ruta = tmp_path / "COOSALUD PARA BRAYAN.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["FACTURA", "OBSERVACION"])
    ws.append(["HUS0000349680", "x"])  # con ceros: prueba la normalizacion
    ws.append(["HUS352629", "x"])
    ws.append(["HUS0000349680", "repetida"])  # duplicada: se procesa una vez
    ws.append(["HUS999999", "no existe en el share"])
    wb.save(ruta)
    return ruta


def _correr(tmp_path: Path, *extra: str) -> Path:
    share = _armar_share(tmp_path)
    excel = _armar_excel(tmp_path)
    destino = tmp_path / "CLASIFICADO"
    argv = [
        "clasificar_regimen_coosalud.py",
        "--excel",
        str(excel),
        "--share",
        str(share),
        "--destino",
        str(destino),
        *extra,
    ]
    viejo = sys.argv
    sys.argv = argv
    try:
        assert cr.main() == 0
    finally:
        sys.argv = viejo
    return destino


def _d(valor: object) -> date | None:
    """openpyxl relee las fechas como datetime: normaliza a date."""
    return valor.date() if isinstance(valor, datetime) else valor  # type: ignore[return-value]


class TestClasificacionYFechas:
    def test_flujo_completo(self, tmp_path):
        destino = _correr(tmp_path)
        salida = destino / "AUDITORIA_FECHAS_REGIMEN.xlsx"
        assert salida.is_file()
        ws = load_workbook(salida)["AUDITORIA"]
        filas = {str(r[0]): r for r in ws.iter_rows(min_row=2, values_only=True)}
        assert set(filas) == {"HUS0000349680", "HUS352629", "HUS999999"}

        f1 = filas["HUS0000349680"]
        assert f1[1] == "Subsidiado"
        assert _d(f1[2]) == date(2026, 5, 1) and _d(f1[3]) == date(2026, 5, 5)  # RIPS
        assert _d(f1[4]) == date(2026, 5, 1) and _d(f1[5]) == date(
            2026, 5, 5
        )  # XML (InvoicePeriod)
        assert f1[6] == "NO"

        f2 = filas["HUS352629"]
        assert f2[1] == "Contributivo"
        assert _d(f2[2]) == date(2026, 6, 3) and _d(f2[3]) == date(
            2026, 6, 3
        )  # AC txt, egreso derivado
        assert _d(f2[4]) == date(2026, 6, 2) and _d(f2[5]) == date(2026, 6, 4)  # Interoperabilidad
        assert f2[6] == "SI"

        f3 = filas["HUS999999"]
        assert f3[1] == "NO_ENCONTRADA"
        assert f3[6] == "SIN DATOS"

    def test_copia_soportes_completos_por_regimen(self, tmp_path):
        destino = _correr(tmp_path)
        sub = destino / "Subsidiado" / "HUS349680"
        con = destino / "Contributivo" / "HUS352629"
        # Va TODO el contenido: XML, PDF, RIPS y CUV.
        assert (sub / "ad090056037001.xml").is_file()
        assert (sub / "soporte_HAM.pdf").is_file()
        assert (sub / "RIPS" / "HUS349680.json").is_file()
        assert (sub / "RIPS" / "ResultadosDoker_HUS349680.json").is_file()
        assert (con / "RIPS" / "US0000001.txt").is_file()
        # La no encontrada no crea carpeta.
        assert not (destino / "SIN_CLASIFICAR").exists()

    def test_sin_copiar_solo_informe(self, tmp_path):
        destino = _correr(tmp_path, "--sin-copiar")
        assert (destino / "AUDITORIA_FECHAS_REGIMEN.xlsx").is_file()
        assert not (destino / "Subsidiado").exists()
        assert not (destino / "Contributivo").exists()


class TestPiezas:
    def test_norm_factura(self):
        assert cr.norm_factura("HUS0000349680") == "HUS349680"
        assert cr.norm_factura(" hus-349 680 ") == "HUS349680"

    def test_regimen_de_tipos_mixto_gana_mayoria(self):
        regimen, detalle = cr.regimen_de_tipos(["04", "04", "01"])
        assert regimen == "Subsidiado"
        assert "MIXTO" in detalle

    def test_cuv_json_no_es_rips(self):
        assert not cr._es_rips_json(CUV_JSON)

    def test_parse_fecha_variantes(self):
        assert cr.parse_fecha("2026-05-01 10:30") == date(2026, 5, 1)
        assert cr.parse_fecha("03/06/2026") == date(2026, 6, 3)
        assert cr.parse_fecha("") is None
        assert cr.parse_fecha("31/31/2026") is None
