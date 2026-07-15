"""Tests del organizador de objeciones EMSSANAR (tools/organizar_objeciones_emssanar.py).

Cubre: parseo de dinero y factura, encabezado del PDF, asignación de columnas por
posición X, reconstrucción de registros (envoltura multilínea, valores en línea
siguiente, códigos apilados, corte por pie de página), fusión de dobles glosas
(valor total + diferencia tarifaria), homologación CUPS→DGH, armado de CRDOBSERV,
filas OBJECIONES y escritura del Excel con los formatos del lote de ejemplo.

El parser de PDF se prueba con una página falsa (duck typing de pdfplumber.Page:
solo necesita extract_words()), así los tests no dependen de un PDF binario.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_objeciones_emssanar as org  # noqa: E402

# ─── Helpers: página falsa estilo pdfplumber ─────────────────────────────────────────

# Centros X representativos de cada columna (dentro de las BANDAS_X del parser)
X_COLS = (60, 150, 210, 293, 340, 450, 620)


def _w(texto: str, col: int, top: float, ancho: float = 10.0) -> dict:
    x0 = X_COLS[col]
    return {"text": texto, "x0": x0, "x1": x0 + ancho, "top": top}


def _linea(top: float, *celdas: tuple[int, str]) -> list[dict]:
    """[(col, 'texto con espacios')...] → palabras separadas en esa línea."""
    palabras = []
    for col, texto in celdas:
        x = X_COLS[col]
        for tok in texto.split():
            palabras.append({"text": tok, "x0": x, "x1": x + 8, "top": top})
            x += 12
    return palabras


class PaginaFalsa:
    def __init__(self, lineas: list[list[dict]]):
        self._palabras = [w for linea in lineas for w in linea]

    def extract_words(self):
        return list(self._palabras)


class PdfFalso:
    def __init__(self, paginas):
        self.pages = paginas


# ─── Parseo básico ───────────────────────────────────────────────────────────────────


def test_parsear_dinero():
    assert org.parsear_dinero("$114.900") == 114900
    assert org.parsear_dinero("$2.177.341") == 2177341
    assert org.parsear_dinero("$700") == 700
    assert org.parsear_dinero("--") is None
    assert org.parsear_dinero("") is None
    assert org.parsear_dinero("114900") is None  # sin $ no es celda de dinero


def test_normalizar_factura():
    assert org.normalizar_factura("HUS515948") == "HUS0000515948"
    assert org.normalizar_factura("HUS 515948") == "HUS0000515948"
    assert org.normalizar_factura("hus0000515948") == "HUS0000515948"
    assert org.normalizar_factura("HUS511916") == "HUS0000511916"


def test_separar_codigo_descripcion():
    assert org.separar_codigo_descripcion("890701 - CONSULTA DE URGENCIAS") == (
        "890701",
        "CONSULTA DE URGENCIAS",
    )
    # el guion del código no se confunde con el separador " - "
    assert org.separar_codigo_descripcion("32606-01 - SODIO LACTATO") == (
        "32606-01",
        "SODIO LACTATO",
    )
    assert org.separar_codigo_descripcion("SOLO TEXTO") == ("SOLO TEXTO", "")


def test_homologar_servicio_sufijo_h():
    assert org.homologar_servicio("876802") == "876802H"  # existe en DGH con H
    assert org.homologar_servicio("890701") == "890701"  # confirmado plano en el lote
    assert org.homologar_servicio("FMQ0923") == "FMQ0923"  # insumos van tal cual
    assert org.homologar_servicio("876802", aplicar_sufijo_h=False) == "876802"


def test_parsear_encabezado():
    texto = (
        "Página 1 de 6\n"
        "Objeción a Factura N° HUS515948\n"
        "EMSSANAR ENTIDAD PROMOTORA DE SALUD SAS\n"
        "Tipo objeción: Glosa\n"
        "Fecha de Objeción: 09-07-2026\n"
        "Valor Factura: $9.895.000\n"
        "Valor Objetado: $2.177.341\n"
    )
    enc = org.parsear_encabezado(texto)
    assert enc["factura"] == "HUS0000515948"
    assert enc["tipo_objecion"] == "Glosa"
    assert enc["fecha_objecion"] == datetime(2026, 7, 9)
    assert enc["valor_factura"] == 9895000
    assert enc["valor_objetado"] == 2177341


def test_tipobj_desde_encabezado():
    assert org.tipobj_desde_encabezado("Glosa") == 0
    assert org.tipobj_desde_encabezado("Devolución") == 2
    assert org.tipobj_desde_encabezado("DEVOLUCION") == 2
    assert org.tipobj_desde_encabezado("") == 0


# ─── Reconstrucción de registros desde palabras ──────────────────────────────────────


def _pagina_basica() -> PaginaFalsa:
    """Dos registros: uno envuelto en 3 líneas y otro con los valores en la
    línea SIGUIENTE al código de tecnología (caso DEXTROSA del PDF real)."""
    lineas = [
        # encabezado de la tabla (debe saltarse, incluida esta misma línea)
        _linea(100, (0, "Tecnología"), (1, "Cantidad"), (5, "Código Objeción"), (6, "Observación")),
        _linea(
            120,
            (0, "890701 - CONSULTA DE"),
            (1, "1"),
            (2, "$114.900"),
            (3, "--"),
            (4, "$24.800"),
            (5, "TA0201 - EL CARGO POR"),
            (6, "sobrefacturado 114900"),
        ),
        _linea(132, (0, "URGENCIAS"), (5, "CONSULTA QUE VIENE"), (6, "reajusta uvb")),
        _linea(144, (5, "RELACIONADO")),
        # registro 2: tecnología sola, números en la línea siguiente
        _linea(156, (0, "1982214-2 - DEXTROSA")),
        _linea(
            168,
            (1, "4"),
            (2, "$20.400"),
            (3, "--"),
            (4, "$3.344"),
            (5, "TA0701 - LOS CARGOS"),
            (6, "mayor valor 4264"),
        ),
        # pie de página: se ignora
        _linea(200, (0, "Reporte generado por ripslink.app")),
    ]
    return PaginaFalsa(lineas)


def test_extraer_registros_basico():
    registros = org.extraer_registros(PdfFalso([_pagina_basica()]))
    assert len(registros) == 2
    r1 = org.consolidar_registro(registros[0])
    assert r1["tec_codigo"] == "890701"
    assert r1["tec_desc"] == "CONSULTA DE URGENCIAS"
    assert r1["cantidad"] == 1
    assert r1["valor_tecnologia"] == 114900
    assert r1["cantidad_objetada"] == "--"
    assert r1["valor_objetado"] == 24800
    assert len(r1["componentes"]) == 1
    assert r1["componentes"][0]["codigo"] == "TA0201"
    assert "EL CARGO POR CONSULTA QUE VIENE RELACIONADO" in r1["componentes"][0]["texto"]
    assert r1["componentes"][0]["observacion"] == "sobrefacturado 114900 reajusta uvb"

    r2 = org.consolidar_registro(registros[1])
    assert r2["tec_codigo"] == "1982214-2"
    assert r2["cantidad"] == 4
    assert r2["valor_objetado"] == 3344
    assert r2["componentes"][0]["codigo"] == "TA0701"


def test_extraer_registros_cruza_paginas():
    """Un registro que sigue en la página siguiente (sin repetir encabezado)."""
    p1 = PaginaFalsa(
        [
            _linea(100, (0, "Tecnología"), (5, "Código"), (6, "Observación")),
            _linea(
                120,
                (0, "902045 - TIEMPO DE"),
                (1, "1"),
                (2, "$70.600"),
                (3, "--"),
                (4, "$15.400"),
                (5, "TA0801 - LOS CARGOS"),
                (6, "sobrefacturado 70600"),
            ),
        ]
    )
    p2 = PaginaFalsa(
        [
            _linea(20, (0, "Página 2 de 2")),
            _linea(40, (0, "PROTROMBINA TP"), (5, "POR APOYO"), (6, "valor de 55200")),
            _linea(
                60,
                (0, "903813 - CLORO"),
                (1, "1"),
                (2, "$22.200"),
                (3, "--"),
                (4, "$4.900"),
                (5, "TA0801 - LOS CARGOS"),
                (6, "sobrefacturado 22200"),
            ),
        ]
    )
    registros = [org.consolidar_registro(r) for r in org.extraer_registros(PdfFalso([p1, p2]))]
    assert len(registros) == 2
    assert registros[0]["tec_desc"] == "TIEMPO DE PROTROMBINA TP"
    assert registros[0]["componentes"][0]["texto"] == "LOS CARGOS POR APOYO"
    assert registros[0]["componentes"][0]["observacion"] == "sobrefacturado 70600 valor de 55200"
    assert registros[1]["tec_codigo"] == "903813"


def test_extraer_registros_codigos_apilados():
    """Un renglón con DOS códigos de objeción apilados (caso FMQ3054 del PDF real):
    el segundo bloque no repite tecnología ni valores → mismo registro."""
    pagina = PaginaFalsa(
        [
            _linea(100, (0, "Tecnología"), (5, "Código"), (6, "Observación")),
            _linea(
                120,
                (0, "FMQ3054 - CANULA"),
                (1, "1"),
                (2, "$10.300"),
                (3, "1"),
                (4, "$10.300"),
                (5, "SO0601 - EXISTE AUSENCIA"),
                (6, "Se objeta el cobro"),
            ),
            _linea(132, (0, "YANKAUER"), (5, "TOTAL O PARCIAL")),
            _linea(144, (5, "FA0603 - SE COBRAN"), (6, "Se glosa CANULA")),
            _linea(156, (5, "DISPOSITIVOS MÉDICOS"), (6, "no se reconoce")),
        ]
    )
    registros = org.extraer_registros(PdfFalso([pagina]))
    assert len(registros) == 1
    r = org.consolidar_registro(registros[0])
    assert r["tec_codigo"] == "FMQ3054"
    assert r["valor_objetado"] == 10300
    assert [c["codigo"] for c in r["componentes"]] == ["SO0601", "FA0603"]
    assert r["componentes"][0]["texto"] == "EXISTE AUSENCIA TOTAL O PARCIAL"
    assert r["componentes"][1]["texto"] == "SE COBRAN DISPOSITIVOS MÉDICOS"
    assert r["componentes"][1]["observacion"] == "Se glosa CANULA no se reconoce"


def test_extraer_registros_corta_en_firmas():
    pagina = PaginaFalsa(
        [
            _linea(100, (0, "Tecnología"), (5, "Código"), (6, "Observación")),
            _linea(
                120,
                (0, "890701 - CONSULTA"),
                (1, "1"),
                (2, "$114.900"),
                (3, "1"),
                (4, "$114.900"),
                (5, "FA0205 - SE COBRAN"),
                (6, "no da lugar"),
            ),
            _linea(140, (0, "Auditor Principal:")),
            _linea(152, (0, "MONTAÑO MINA ELOISA - AUDITOR EN SALUD")),
        ]
    )
    registros = org.extraer_registros(PdfFalso([pagina]))
    assert len(registros) == 1
    r = org.consolidar_registro(registros[0])
    # la línea del auditor no debe contaminar la tecnología
    assert r["tec_desc"] == "CONSULTA"


# ─── Fusión de dobles glosas ─────────────────────────────────────────────────────────


def _renglon(tec: str, cant_obj: str, valor: int, codigo: str) -> dict:
    return {
        "tec_codigo": tec,
        "tec_desc": f"DESC {tec}",
        "cantidad": 1,
        "valor_tecnologia": valor,
        "cantidad_objetada": cant_obj,
        "valor_objetado": valor,
        "componentes": [{"codigo": codigo, "texto": f"TEXTO {codigo}", "observacion": "nota"}],
    }


def test_fusionar_dobles_glosas():
    renglones = [
        _renglon("890701", "--", 24800, "TA0201"),  # diferencia tarifaria
        _renglon("890701", "1", 114900, "FA0205"),  # valor total → absorbe la anterior
        _renglon("902045", "--", 15400, "TA0801"),  # sola, queda igual
    ]
    fusionados = org.fusionar_dobles_glosas(renglones)
    assert len(fusionados) == 2
    principal = next(r for r in fusionados if r["tec_codigo"] == "890701")
    assert principal["componentes"][0]["codigo"] == "FA0205"
    assert principal["valor_objetado"] == 114900
    assert [x["componentes"][0]["codigo"] for x in principal["fusionados"]] == ["TA0201"]
    # la suma final reproduce el "Valor Objetado" del encabezado (sin doble conteo)
    assert sum(r["valor_objetado"] for r in fusionados) == 114900 + 15400


def test_fusionar_respeta_sobrantes():
    """3 diferencias tarifarias y 2 totales del mismo servicio: se fusionan 2 pares
    y la tercera diferencia queda como fila propia (caso 906913 del PDF real)."""
    renglones = [
        _renglon("906913", "--", 21600, "TA0801"),
        _renglon("906913", "--", 21600, "TA0801"),
        _renglon("906913", "--", 21600, "TA0801"),
        _renglon("906913", "1", 98600, "CL0801"),
        _renglon("906913", "1", 98600, "CL0801"),
    ]
    fusionados = org.fusionar_dobles_glosas(renglones)
    assert len(fusionados) == 3
    assert sum(r["valor_objetado"] for r in fusionados) == 21600 + 98600 * 2


def test_fusionar_no_cruza_tecnologias():
    renglones = [
        _renglon("890701", "--", 24800, "TA0201"),
        _renglon("999999", "1", 50000, "FA0205"),
    ]
    fusionados = org.fusionar_dobles_glosas(renglones)
    assert len(fusionados) == 2
    assert all("fusionados" not in r for r in fusionados)


# ─── CRDOBSERV y filas ───────────────────────────────────────────────────────────────


def test_armar_crdobserv_simple():
    r = _renglon("902045", "--", 15400, "TA0801")
    txt = org.armar_crdobserv(r)
    assert txt == "TA0801 TEXTO TA0801 (902045-DESC 902045): NOTA$15400"


def test_armar_crdobserv_fusionado():
    principal = _renglon("890701", "1", 114900, "FA0205")
    principal["fusionados"] = [_renglon("890701", "--", 24800, "TA0201")]
    txt = org.armar_crdobserv(principal)
    lineas = txt.split("\n")
    assert len(lineas) == 2
    assert lineas[0].startswith("FA0205 ") and lineas[0].endswith("$114900")
    assert lineas[1].startswith("TA0201 ") and lineas[1].endswith("$24800")


def test_armar_crdobserv_codigo_apilado_sin_valor():
    r = _renglon("FMQ3054", "1", 10300, "SO0601")
    r["componentes"].append({"codigo": "FA0603", "texto": "SE COBRAN", "observacion": ""})
    txt = org.armar_crdobserv(r)
    lineas = txt.split("\n")
    assert lineas[0].endswith("$10300")
    assert lineas[1] == "FA0603 SE COBRAN (FMQ3054-DESC FMQ3054)"


def test_renglon_a_fila():
    r = _renglon("876802", "--", 20300, "TA0801")
    fila = org.renglon_a_fila(
        r,
        consec=7,
        factura="HUS0000515948",
        fecha=datetime(2026, 7, 9),
        usuario="999",
        tipobj=0,
    )
    assert fila["CDCONSEC"] == "7"
    assert fila["CRNCXC"] == "HUS0000515948"
    assert fila["CDFECDOC"] == fila["CROFECOBJ"] == datetime(2026, 7, 9)
    assert fila["CROCLAOBJ"] == 0
    assert fila["GENUSUARIO4"] == "999"
    assert fila["CRNCONOBJ"] == "TA0801"
    assert fila["SLNSERPRO"] == "876802H"  # homologado a DGH
    assert fila["CROVALOBJ"] == 20300
    assert fila["CROTIPOBJ"] == 0
    assert fila["CROREFERE"] is None and fila["IDRIPS"] is None


# ─── Excel ───────────────────────────────────────────────────────────────────────────


def test_escribir_excel(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    r = _renglon("902045", "--", 15400, "TA0801")
    fila = org.renglon_a_fila(
        r, consec=1, factura="HUS0000515948", fecha=datetime(2026, 7, 9), usuario="999", tipobj=0
    )
    salida = tmp_path / "OBJECIONES_TEST.xlsx"
    org.escribir_excel([fila], salida)

    wb = openpyxl.load_workbook(str(salida))
    assert wb.sheetnames == ["OBJECIONES"]
    ws = wb["OBJECIONES"]
    assert [c.value for c in ws[1]] == org.COLUMNAS_OBJECIONES
    valores = {c.value for c in ws[2]}
    assert "HUS0000515948" in valores
    # tipos/formatos como el lote de ejemplo: consecutivo texto, valor numérico
    assert ws.cell(row=2, column=1).value == "1"
    assert ws.cell(row=2, column=1).number_format == "@"
    assert ws.cell(row=2, column=14).value == 15400
    assert ws.cell(row=2, column=2).value == datetime(2026, 7, 9)
    assert ws.cell(row=2, column=16).value == 0


def test_buscar_pdfs(tmp_path):
    (tmp_path / "sub").mkdir()
    a = tmp_path / "DETALLES_DE_SERVICIOS_FACTURA_HUS0000515948.pdf"
    b = tmp_path / "sub" / "DETALLES_DE_SERVICIOS_FACTURA_HUS0000515949.pdf"
    otro = tmp_path / "OTRA_COSA.pdf"
    for f in (a, b, otro):
        f.write_bytes(b"%PDF-1.4")
    # carpeta: solo los DETALLES_*, recursivo; archivo suelto: tal cual
    assert org.buscar_pdfs([str(tmp_path)]) == [a, b]
    assert org.buscar_pdfs([str(otro)]) == [otro]
    # sin duplicados si se pasa carpeta + archivo
    assert org.buscar_pdfs([str(tmp_path), str(a)]) == [a, b]
