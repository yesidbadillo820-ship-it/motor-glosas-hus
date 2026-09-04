"""Pruebas del bot RPA del lote Dispensario: cruce tarifario del contrato 440,
lectura en cascada de la factura, búsqueda de soportes y enriquecimiento del
Excel sin inventar datos."""

import sys
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

RAIZ = Path(__file__).resolve().parents[2] / "tools" / "glosas_dispensario"
sys.path.insert(0, str(RAIZ))

from bot_lote_dispensario import buscar_pdf_factura, enriquecer_excel, frase_anclaje  # noqa: E402
from tarifario_440 import cargar_tarifario, frase_tarifaria, tarifa_de  # noqa: E402


# ── Tarifario del contrato 440 ──────────────────────────────────────────────
def _tarifario_servicios(ruta):
    wb = Workbook()
    ws = wb.active
    ws.title = "SERVICIOS DE PROCEDIMIENTOS"
    ws.append(
        [
            "ITEM",
            "CUPS",
            "DESCRIPCION CUPS",
            "CODIGO IPS",
            "DESCRIPCION IPS",
            "PRECIO DE REFERENCIA",
            "TARIFA A LA QUE CORRESPONDE",
        ]
    )
    ws.append(
        [1, "039001", "INSERCION DE CATETER", "039001H", "INSERCION DE CATETER", 1689585, "PROPIA"]
    )
    ws.append([2, "902210", "HEMOGRAMA IV", "902210AMB", "HEMOGRAMA IV", 17556.5, "PROPIA"])
    wb.save(ruta)


def _tarifario_medicamentos(ruta):
    wb = Workbook()
    ws = wb.active
    ws.title = "ANEXO 01-MX REGULADOS"
    ws.append(["CODIGO CUM", "CÓDIGO ATC", "NOMBRE", "PRECIO DE VENTA", "NORMATIVA VIGENTE"])
    ws.append(["20103720-02", "J05AR02", "ABACAVIR 600 MG", 31361, "CIRCULAR 19 DE 2024"])
    wb.save(ruta)


def test_tarifario_cruza_por_codigo_ips_cups_y_cum(tmp_path):
    serv, mx = tmp_path / "serv.xlsx", tmp_path / "mx.xlsx"
    _tarifario_servicios(serv)
    _tarifario_medicamentos(mx)
    idx = cargar_tarifario(serv, mx)

    assert tarifa_de(idx, "039001H")["precio"] == 1689585  # codigo IPS exacto
    assert tarifa_de(idx, "039001")["precio"] == 1689585  # CUPS pelado
    assert (
        tarifa_de(idx, "902210amb")["precio"] == 17557
        or tarifa_de(idx, "902210amb")["precio"] == 17556
    )
    assert tarifa_de(idx, "20103720-02")["precio"] == 31361  # CUM completo
    assert tarifa_de(idx, "20103720")["precio"] == 31361  # CUM sin presentacion
    assert tarifa_de(idx, "999999") is None  # sin pacto: no se cita nada
    frase = frase_tarifaria("039001H", tarifa_de(idx, "039001H"))
    assert "CONTRATO 440-DIGSA-DMBUG-2025" in frase and "$1.689.585" in frase


def test_tarifario_sin_archivos_devuelve_indice_vacio(tmp_path):
    assert cargar_tarifario(tmp_path / "no.xlsx", None) == {}


# ── Busqueda de soportes en las carpetas de radicacion ──────────────────────
def test_busca_el_pdf_en_el_mes_mas_reciente_primero(tmp_path):
    viejo = tmp_path / "3. MARZO 2026 - SOPORTES RADICACION"
    nuevo = tmp_path / "9.SEPTIEMBRE - SOPORTES RADICACION"
    (viejo / "sub").mkdir(parents=True)
    nuevo.mkdir()
    (viejo / "sub" / "FEV_HUS0000540273.pdf").write_bytes(b"%PDF viejo")
    (nuevo / "HUS0000540273 RADICADO.pdf").write_bytes(b"%PDF nuevo")
    hallado = buscar_pdf_factura("HUS0000540273", [str(viejo), str(nuevo)])
    assert hallado is not None and hallado.parent == nuevo
    assert buscar_pdf_factura("HUS0000999999", [str(viejo), str(nuevo)]) is None


# ── No invencion y enriquecimiento del Excel ────────────────────────────────
def test_sin_datos_leidos_no_hay_frase_de_anclaje():
    assert frase_anclaje("HUS0000500001", dict(paciente=None, total=None)) is None
    frase = frase_anclaje("HUS0000500001", dict(paciente="PEREZ JUAN", total=123456))
    assert "PEREZ JUAN" in frase and "$123.456" in frase


def test_enriquecer_inserta_antes_del_cierre_y_es_idempotente(tmp_path):
    ruta = tmp_path / "resp.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Respuestas Glosa"
    ws.append(
        [
            "Factura",
            "# Objeción",
            "Cód.",
            "Servicio",
            "Valor Objetado",
            "Valor Aceptado",
            "Cod Respuesta",
            "Detalle Respuesta",
        ]
    )
    detalle = "ESE HUS NO ACEPTA LA GLOSA... POR LO EXPUESTO, SE SOLICITA EL LEVANTAMIENTO TOTAL."
    ws.append(["HUS0000500001", 1, "TA0601", "890201 - CONSULTA", 1000, 0, "RE9901", detalle])
    ws.append(["HUS0000500001", 3, "TA0201", "890301 - CONSULTA", 2000, 0, "RE9901", detalle])
    wb.save(ruta)

    tocadas = enriquecer_excel(
        ruta,
        por_factura={"HUS0000500001": "LA FACTURA SE ANEXA."},
        por_linea={("HUS0000500001", 3): "LA TARIFA PACTADA ES DE $9.999."},
    )
    assert tocadas == 2
    filas = list(load_workbook(ruta)["Respuestas Glosa"].iter_rows(min_row=2, values_only=True))
    # la frase queda ANTES del cierre institucional
    assert filas[0][7].index("LA FACTURA SE ANEXA.") < filas[0][7].index("POR LO EXPUESTO")
    assert "LA TARIFA PACTADA" not in filas[0][7]
    assert filas[1][7].index("LA TARIFA PACTADA ES DE $9.999.") < filas[1][7].index(
        "LA FACTURA SE ANEXA."
    )
    # repetir no duplica
    assert enriquecer_excel(ruta, {"HUS0000500001": "LA FACTURA SE ANEXA."}, {}) == 0


# ── Lectura en cascada (pdfplumber como primer intento) ─────────────────────
def test_cascada_lee_paciente_y_total_con_pdfplumber(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("pdfplumber")
    from extraer_factura_pdf import extraer_datos_factura

    ruta = tmp_path / "factura.pdf"
    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.insert_text((72, 100), "FACTURA ELECTRONICA DE VENTA HUS0000540273")
    pagina.insert_text((72, 130), "PACIENTE: RODRIGUEZ GOMEZ MARIA FERNANDA")
    pagina.insert_text((72, 160), "VALOR TOTAL: $ 1.234.567")
    doc.save(ruta)
    doc.close()

    datos = extraer_datos_factura(ruta)
    assert datos["ok"] and datos["metodo"] in ("pdfplumber", "PyPDF2")
    assert datos["paciente"] == "RODRIGUEZ GOMEZ MARIA FERNANDA"
    assert datos["total"] == 1234567


def test_cascada_sin_texto_ni_ocr_no_inventa(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from extraer_factura_pdf import extraer_datos_factura

    ruta = tmp_path / "escaneada.pdf"
    doc = pymupdf.open()
    doc.new_page()  # pagina en blanco: nada que leer sin OCR
    doc.save(ruta)
    doc.close()

    datos = extraer_datos_factura(ruta)
    assert datos["paciente"] is None and datos["total"] is None
    assert not datos["ok"] and datos["metodo"].startswith("SIN_LECTURA")
