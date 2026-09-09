"""Pruebas de tools/clasificar_regimen_coosalud.py.

Arman un share falso con la estructura real
(<share>/AAAAMM/FACTURAS_SALUD/<factura>/ con XML DIAN + RIPS + PDF) y verifican:
regimen por tipoUsuario del RIPS JSON y por el US de los RIPS TXT viejos,
fechas de la factura con la prioridad aprendida de la factura real HUS349680
(PDF impreso → Interoperabilidad → solo StartDate del InvoicePeriod; el
EndDate NUNCA se usa como egreso porque es la fecha de facturacion), la
busqueda de soportes en las rutas de radicacion, la copia de carpetas por
regimen y el Excel de auditoria.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import clasificar_regimen_coosalud as cr  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

# InvoicePeriod real del HUS: EndDate = fecha de facturacion (07/05), NO el
# egreso clinico (05/05). El extractor no debe usar ese EndDate jamas.
XML_SUBSIDIADO = """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cac:Attachment><cac:ExternalReference><cbc:Description><![CDATA[
    <Invoice>
      <cbc:ID>HUS349680</cbc:ID>
      <cbc:IssueDate>2026-05-07</cbc:IssueDate>
      <cac:InvoicePeriod>
        <cbc:StartDate>2026-05-01</cbc:StartDate>
        <cbc:StartTime>09:00:00-05:00</cbc:StartTime>
        <cbc:EndDate>2026-05-07</cbc:EndDate>
        <cbc:EndTime>16:09:06-05:00</cbc:EndTime>
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

# Texto como lo devuelve PyMuPDF sobre el fv*.pdf real del HUS.
TEXTO_PDF_C1 = (
    "FACTURA ELECTRONICA DE VENTA HUS349680\n"
    "CLIENTE COOSALUD ENTIDAD PROMOTORA DE SALUD S.A. SUBSIDIADO\n"
    "Fec Ingreso 01 may. 2026 09:00 a. m.\n"
    "Fec Egreso 05 may. 2026 02:15 p. m.\n"
)

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

    # Factura 1: subsidiado, RIPS JSON, PDF con fechas clinicas.
    c1 = share / "202605" / "FACTURAS_SALUD" / "HUS349680"
    (c1 / "RIPS").mkdir(parents=True)
    (c1 / "ad090056037001.xml").write_text(XML_SUBSIDIADO, encoding="utf-8")
    (c1 / "fv090056037001.pdf").write_bytes(b"%PDF-1.4 fake")
    (c1 / "RIPS" / "HUS349680.json").write_text(json.dumps(RIPS_JSON_SUBSIDIADO), encoding="utf-8")
    (c1 / "RIPS" / "ResultadosDoker_HUS349680.json").write_text(
        json.dumps(CUV_JSON), encoding="utf-8"
    )
    (c1 / "soporte_HAM.pdf").write_bytes(b"%PDF-1.4 fake")

    # Factura 2: contributivo por US de RIPS TXT viejo; solo consultas (egreso
    # derivado); fechas de factura desde Interoperabilidad (sin PDF fv).
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


def _armar_radicacion(tmp_path: Path) -> tuple[Path, Path]:
    """Dos raices con la estructura real de los servidores de radicacion."""
    r1 = tmp_path / "radicacion1"
    # Carpeta por factura (se copia completa).
    d1 = r1 / "COOSALUD" / "GESTORA" / "ENV-226686-OK" / "HUS349680"
    d1.mkdir(parents=True)
    (d1 / "FEV_900006037_HUS349680.pdf").write_bytes(b"%PDF fev")
    (d1 / "HEV_900006037_HUS349680.pdf").write_bytes(b"%PDF hev")
    # Carpeta de OTRA factura: la poda no debe entrar ni copiarla.
    d_ajena = r1 / "COOSALUD" / "GESTORA" / "ENV-226686-OK" / "HUS999777"
    d_ajena.mkdir(parents=True)
    (d_ajena / "FEV_900006037_HUS999777.pdf").write_bytes(b"%PDF ajena")

    r2 = tmp_path / "radicacion2"
    # Archivo suelto con el numero en el nombre (sin carpeta por factura).
    suelto = r2 / "SINAC" / "FEBRERO"
    suelto.mkdir(parents=True)
    (suelto / "900006037_HUS352629_FACTURA.pdf").write_bytes(b"%PDF suelto")
    return r1, r2


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


def _correr(tmp_path: Path, *extra: str, soportes: bool = False) -> Path:
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
    ]
    if not soportes:
        argv.append("--sin-soportes")
    argv.extend(extra)
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


def _filas(destino: Path) -> dict[str, tuple]:
    ws = load_workbook(destino / "AUDITORIA_FECHAS_REGIMEN.xlsx")["AUDITORIA"]
    return {str(r[0]): r for r in ws.iter_rows(min_row=2, values_only=True)}


# Indices de columna en el Excel de auditoria.
COL_REGIMEN = 1
COL_RIPS_AT, COL_RIPS_EG, COL_FAC_IN, COL_FAC_EG = 2, 3, 4, 5
COL_ALERTA = 6
COL_FUENTE_FECHAS = 10
COL_SOP_ORIGEN, COL_SOP_ARCHIVOS = 12, 13


class TestClasificacionYFechas:
    def test_flujo_completo(self, tmp_path, monkeypatch):
        # El PDF fv de la factura 1 "se lee" con el texto real del HUS.
        monkeypatch.setattr(
            cr, "_texto_pdf", lambda ruta: TEXTO_PDF_C1 if ruta.name.startswith("fv") else ""
        )
        destino = _correr(tmp_path)
        filas = _filas(destino)
        assert set(filas) == {"HUS0000349680", "HUS352629", "HUS999999"}

        f1 = filas["HUS0000349680"]
        assert f1[COL_REGIMEN] == "Subsidiado"
        assert _d(f1[COL_RIPS_AT]) == date(2026, 5, 1) and _d(f1[COL_RIPS_EG]) == date(2026, 5, 5)
        # Fechas de la factura desde el PDF impreso (no del InvoicePeriod).
        assert _d(f1[COL_FAC_IN]) == date(2026, 5, 1) and _d(f1[COL_FAC_EG]) == date(2026, 5, 5)
        assert f1[COL_ALERTA] == "NO"
        assert "PDF factura" in str(f1[COL_FUENTE_FECHAS])

        f2 = filas["HUS352629"]
        assert f2[COL_REGIMEN] == "Contributivo"
        assert _d(f2[COL_RIPS_AT]) == date(2026, 6, 3) and _d(f2[COL_RIPS_EG]) == date(2026, 6, 3)
        assert _d(f2[COL_FAC_IN]) == date(2026, 6, 2) and _d(f2[COL_FAC_EG]) == date(2026, 6, 4)
        assert f2[COL_ALERTA] == "SI"
        assert "Interoperabilidad" in str(f2[COL_FUENTE_FECHAS])

        f3 = filas["HUS999999"]
        assert f3[COL_REGIMEN] == "NO_ENCONTRADA"
        assert f3[COL_ALERTA] == "SIN DATOS"

    def test_sin_pdf_legible_no_se_inventa_el_egreso(self, tmp_path):
        # Solo XML (el PDF fake no es legible): ingreso sale del StartDate,
        # pero el EndDate (fecha de facturacion) JAMAS se usa como egreso.
        destino = _correr(tmp_path)
        f1 = _filas(destino)["HUS0000349680"]
        assert _d(f1[COL_FAC_IN]) == date(2026, 5, 1)
        assert f1[COL_FAC_EG] is None
        assert f1[COL_ALERTA] == "SIN DATOS"
        assert "Factura_Egreso" in str(f1[7])  # Detalle: faltan ...
        assert "solo ingreso" in str(f1[COL_FUENTE_FECHAS])

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

    def test_excel_abierto_no_pierde_la_corrida(self, tmp_path, monkeypatch):
        """Si el Excel de auditoria esta abierto (PermissionError de Windows),
        el informe se guarda con sufijo de hora en vez de reventar al final."""
        import openpyxl

        original = openpyxl.Workbook.save
        bloqueado = {"ya": False}

        def save_con_bloqueo(self, filename):
            if str(filename).endswith("AUDITORIA_FECHAS_REGIMEN.xlsx") and not bloqueado["ya"]:
                bloqueado["ya"] = True
                raise PermissionError(13, "Permission denied", str(filename))
            return original(self, filename)

        monkeypatch.setattr(openpyxl.Workbook, "save", save_con_bloqueo)
        destino = _correr(tmp_path, "--sin-copiar")
        assert not (destino / "AUDITORIA_FECHAS_REGIMEN.xlsx").exists()
        respaldos = list(destino.glob("AUDITORIA_FECHAS_REGIMEN_*.xlsx"))
        assert len(respaldos) == 1
        ws = load_workbook(respaldos[0])["AUDITORIA"]
        assert ws.max_row == 4  # encabezado + 3 facturas: no se perdio nada


class TestSoportesRadicacion:
    def test_busca_y_copia_soportes(self, tmp_path):
        r1, r2 = _armar_radicacion(tmp_path)
        destino = _correr(
            tmp_path,
            "--raiz-soportes",
            str(r1),
            "--raiz-soportes",
            str(r2),
            soportes=True,
        )
        # Carpeta completa de la factura 1 copiada bajo SOPORTES_RADICACION\.
        sop1 = destino / "Subsidiado" / "HUS349680" / "SOPORTES_RADICACION" / "HUS349680"
        assert (sop1 / "FEV_900006037_HUS349680.pdf").is_file()
        assert (sop1 / "HEV_900006037_HUS349680.pdf").is_file()
        # Archivo suelto de la factura 2.
        sop2 = destino / "Contributivo" / "HUS352629" / "SOPORTES_RADICACION"
        assert (sop2 / "900006037_HUS352629_FACTURA.pdf").is_file()
        # La factura ajena (poda) no se copio a ningun lado.
        assert not any("999777" in p.name for p in destino.rglob("*"))
        # Columnas del informe.
        filas = _filas(destino)
        assert filas["HUS0000349680"][COL_SOP_ARCHIVOS] == 2
        assert "HUS349680" in str(filas["HUS0000349680"][COL_SOP_ORIGEN])
        assert filas["HUS352629"][COL_SOP_ARCHIVOS] == 1
        # La que no tiene soportes lo dice en observaciones.
        assert "sin soportes en las rutas" not in str(filas["HUS0000349680"][16] or "")

    def test_formato_lote_para_el_cargue_de_coosalud(self, tmp_path):
        """Con --lote la salida queda como la pide el portal:
        <Regimen>\\<lote>\\RIPS\\HUS<n>.json (+CUV) y \\IMG\\HUS<n>\\<soportes>."""
        r1, r2 = _armar_radicacion(tmp_path)
        destino = _correr(
            tmp_path,
            "--raiz-soportes",
            str(r1),
            "--raiz-soportes",
            str(r2),
            "--lote",
            "605505_20260908_135357",
            soportes=True,
        )
        lote = destino / "Subsidiado" / "605505_20260908_135357"
        # RIPS planos y renombrados al nombre que espera el portal.
        assert (lote / "RIPS" / "HUS349680.json").is_file()
        assert (lote / "RIPS" / "CUV_HUS349680.json").is_file()
        # Soportes del servicio en IMG\<factura>\ (aplanados).
        img = lote / "IMG" / "HUS349680"
        assert (img / "FEV_900006037_HUS349680.pdf").is_file()
        assert (img / "HEV_900006037_HUS349680.pdf").is_file()
        # La contributiva arma su propio lote bajo su regimen.
        lote_c = destino / "Contributivo" / "605505_20260908_135357"
        assert (lote_c / "IMG" / "HUS352629" / "900006037_HUS352629_FACTURA.pdf").is_file()
        # Ya NO se crea la carpeta por factura del formato viejo.
        assert not (destino / "Subsidiado" / "HUS349680").exists()

    def test_indexar_radicacion_no_desciende_a_facturas_ajenas(self, tmp_path):
        r1, _ = _armar_radicacion(tmp_path)
        idx = cr.indexar_radicacion([r1], {"349680"})
        assert [p.name for p in idx["349680"]] == ["HUS349680"]

    def test_estructura_env_img_como_la_real(self, tmp_path):
        """La estructura real que reporto el auditor:
        <raiz>\\COOSALUD\\KARIN\\ENV-222670-OK-C-DGH\\IMG\\HUS472660\\*.pdf"""
        raiz = tmp_path / "3. MARZO 2026 - SOPORTES RADICACION"
        carpeta = raiz / "COOSALUD" / "KARIN" / "ENV-222670-OK-C-DGH" / "IMG" / "HUS472660"
        carpeta.mkdir(parents=True)
        for pref in ("CRC", "EPI", "FEV", "HAM"):
            (carpeta / f"{pref}_900006037_HUS472660.pdf").write_bytes(b"%PDF")
        (carpeta / "HUS472660.xml").write_text("<x/>", encoding="utf-8")
        idx = cr.indexar_radicacion([raiz], {"472660"})
        assert [p.name for p in idx["472660"]] == ["HUS472660"]
        copiados, obs = cr.copiar_soportes(idx["472660"], tmp_path / "out")
        assert copiados == 5 and obs == []

    def test_lista_txt_procesa_facturas_sin_excel(self, tmp_path):
        share = _armar_share(tmp_path)
        destino = tmp_path / "CLASIFICADO"
        # TXT como lo deja PowerShell (`>` = UTF-16 con BOM), con duplicada,
        # comillas, linea vacia y comentario.
        lista = tmp_path / "facturas.txt"
        lista.write_bytes(
            '﻿HUS0000349680\n\n# comentario\n"HUS352629"\nHUS349680\n'.encode("utf-16")
        )
        argv = [
            "clasificar_regimen_coosalud.py",
            "--lista",
            str(lista),
            "--share",
            str(share),
            "--destino",
            str(destino),
            "--sin-soportes",
        ]
        viejo = sys.argv
        sys.argv = argv
        try:
            assert cr.main() == 0
        finally:
            sys.argv = viejo
        filas = _filas(destino)
        assert set(filas) == {"HUS0000349680", "HUS352629"}  # deduplicada

    def test_solo_procesa_facturas_puntuales_sin_excel(self, tmp_path):
        share = _armar_share(tmp_path)
        destino = tmp_path / "CLASIFICADO"
        argv = [
            "clasificar_regimen_coosalud.py",
            "--solo",
            "HUS0000349680",
            "--share",
            str(share),
            "--destino",
            str(destino),
            "--sin-soportes",
        ]
        viejo = sys.argv
        sys.argv = argv
        try:
            assert cr.main() == 0
        finally:
            sys.argv = viejo
        filas = _filas(destino)
        assert set(filas) == {"HUS0000349680"}
        assert filas["HUS0000349680"][COL_REGIMEN] == "Subsidiado"

    def test_resolver_raices_deduplica_equivalentes(self, tmp_path, monkeypatch):
        # Y:\X y \\Prime\radicacion_2026\X canonizan igual → una sola pasada.
        assert cr._canon_raiz(r"Y:\3. MARZO 2026") == cr._canon_raiz(
            "\\\\Prime\\radicacion_2026\\3. MARZO 2026"
        )
        # Lo mismo para X: ≡ \\Prime\servidor_radicación (con tilde).
        assert cr._canon_raiz(r"X:\RADICACION DIGITAL") == cr._canon_raiz(
            "\\\\Prime\\servidor_radicación\\RADICACION DIGITAL"
        )
        # Con rutas reales (tmp) el resolver deja pasar las accesibles y avisa
        # (sin reventar) las inexistentes.
        existente = tmp_path / "raiz_ok"
        existente.mkdir()
        out = cr.resolver_raices([str(existente), str(tmp_path / "no_existe")])
        assert out == [existente]


class TestPiezas:
    def test_norm_factura(self):
        assert cr.norm_factura("HUS0000349680") == "HUS349680"
        assert cr.norm_factura(" hus-349 680 ") == "HUS349680"

    def test_clave_numerica(self):
        assert cr.clave_numerica("HUS0000349680") == "349680"
        assert cr.clave_numerica("FEV_900006037_HUS349680.pdf") == "349680"
        assert cr.clave_numerica("349680") == "349680"

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

    def test_fechas_desde_texto_pdf_formato_real(self):
        # Texto tal cual lo devuelve PyMuPDF sobre el fv*.pdf real del HUS.
        texto = "Fec Ingreso 07 feb. 2025 11:02 a. m.\nFec Egreso 10 feb. 2025 12:15 p. m."
        fechas = cr._fechas_desde_texto_pdf(texto)
        assert fechas == {"ingreso": date(2025, 2, 7), "egreso": date(2025, 2, 10)}

    def test_analizar_factura_ignora_el_enddate(self, tmp_path):
        carpeta = tmp_path / "HUS349680"
        carpeta.mkdir()
        (carpeta / "ad001.xml").write_text(XML_SUBSIDIADO, encoding="utf-8")
        d = cr.analizar_factura(carpeta)
        assert d.ingreso == date(2026, 5, 1)
        assert d.egreso is None  # EndDate=2026-05-07 (facturacion) NO se usa
        assert "solo ingreso" in d.fuente
        assert any("no trae egreso clinico" in o for o in d.obs)
