"""
Pruebas de nucleo.excel_tools (unir varios Excel en uno, sin dañar el dato).

Se prueban con archivos reales generados en memoria: los dos modos (apilar /
hojas), la preservación de tipos (fechas y números nunca a texto), el salto
de filas de título, la unión de columnas nuevas y las entradas mixtas
(archivo suelto, carpeta, zip).
"""

import os
import sys
import zipfile

import pytest

SUITE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "tools", "suite_cartera_hus")
)
if SUITE not in sys.path:
    sys.path.insert(0, SUITE)

openpyxl = pytest.importorskip("openpyxl")

from nucleo import excel_tools  # noqa: E402

FECHA = __import__("datetime").datetime(2026, 1, 15)


def _silencio(_):
    pass


def _xlsx(ruta, filas, titulo=None):
    """Crea un Excel real; `titulo` agrega una fila suelta encima del encabezado."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if titulo:
        ws.append([titulo])
    for fila in filas:
        ws.append(fila)
    wb.save(ruta)
    return str(ruta)


# ------------------------------------------------------------- resolver entradas


def test_resolver_entradas_mixtas(tmp_path):
    a = _xlsx(tmp_path / "a.xlsx", [["H1", "H2"], [1, 2]])
    carpeta = tmp_path / "carpeta"
    carpeta.mkdir()
    _xlsx(carpeta / "b.xlsx", [["H1", "H2"], [3, 4]])
    (carpeta / "~$abierto.xlsx").write_bytes(b"x")  # temporal de Excel: ignorar
    (carpeta / "notas.txt").write_text("ignorar")
    zpath = tmp_path / "c.zip"
    c = _xlsx(tmp_path / "c.xlsx", [["H1", "H2"], [5, 6]])
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(c, "c.xlsx")

    rutas = excel_tools._resolver_entradas([a, str(carpeta), str(zpath)])
    nombres = [os.path.basename(r) for r in rutas]
    assert nombres == ["a.xlsx", "b.xlsx", "c.xlsx"]


# ------------------------------------------------------------- modo apilar


def test_apilar_preserva_tipos_y_marca_origen(tmp_path):
    a = _xlsx(tmp_path / "enero.xlsx", [["FACTURA", "FECHA", "VALOR"], ["HUS1", FECHA, 150000]])
    b = _xlsx(tmp_path / "febrero.xlsx", [["FACTURA", "FECHA", "VALOR"], ["HUS2", FECHA, 99.5]])
    salida = str(tmp_path / "unido.xlsx")
    assert excel_tools.unir([a, b], salida, modo="apilar", log=_silencio) == salida

    ws = openpyxl.load_workbook(salida, data_only=True)["UNIDO"]
    hdrs = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    assert hdrs == ["FACTURA", "FECHA", "VALOR", "_ARCHIVO_ORIGEN"]
    assert ws.max_row - 1 == 2
    # la fecha sigue siendo fecha y el monto sigue siendo número, NUNCA texto
    assert hasattr(ws.cell(2, 2).value, "year")
    assert isinstance(ws.cell(2, 3).value, (int, float)) and ws.cell(2, 3).value == 150000
    assert ws.cell(3, 3).value == 99.5
    assert ws.cell(2, 4).value == "enero.xlsx"
    assert ws.cell(3, 4).value == "febrero.xlsx"


def test_apilar_salta_titulo_y_une_columnas_nuevas(tmp_path):
    a = _xlsx(tmp_path / "a.xlsx", [["FACTURA", "VALOR"], ["HUS1", 100]])
    b = _xlsx(
        tmp_path / "b.xlsx",
        [["FACTURA", "VALOR", "ESTADO"], ["HUS2", 200, "PAGADA"]],
        titulo="INFORME DE CARTERA",
    )
    salida = str(tmp_path / "unido.xlsx")
    excel_tools.unir([a, b], salida, modo="apilar", log=_silencio)

    ws = openpyxl.load_workbook(salida, data_only=True)["UNIDO"]
    hdrs = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    # la columna nueva se agrega al final: ninguna columna ni fila se pierde
    assert hdrs == ["FACTURA", "VALOR", "ESTADO", "_ARCHIVO_ORIGEN"]
    assert ws.max_row - 1 == 2
    assert ws.cell(3, 3).value == "PAGADA"
    assert ws.cell(2, 3).value is None  # el archivo sin ESTADO queda vacío ahí


def test_apilar_resumen_cuenta_por_archivo(tmp_path):
    a = _xlsx(tmp_path / "a.xlsx", [["H"], ["x"], ["y"]])
    b = _xlsx(tmp_path / "b.xlsx", [["H"], ["z"]])
    salida = str(tmp_path / "unido.xlsx")
    excel_tools.unir([a, b], salida, modo="apilar", log=_silencio)

    ws2 = openpyxl.load_workbook(salida, data_only=True)["RESUMEN"]
    conteos = {ws2.cell(r, 1).value: ws2.cell(r, 2).value for r in (2, 3)}
    assert conteos == {"a.xlsx": 2, "b.xlsx": 1}


def test_apilar_archivo_corrupto_no_tumba_el_resto(tmp_path):
    bueno = _xlsx(tmp_path / "bueno.xlsx", [["H"], ["dato"]])
    roto = tmp_path / "roto.xlsx"
    roto.write_bytes(b"esto no es un excel")
    salida = str(tmp_path / "unido.xlsx")
    excel_tools.unir([bueno, str(roto)], salida, modo="apilar", log=_silencio)

    wb = openpyxl.load_workbook(salida, data_only=True)
    assert wb["UNIDO"].max_row - 1 == 1
    texto_resumen = " ".join(
        str(wb["RESUMEN"].cell(r, 3).value or "") for r in range(2, wb["RESUMEN"].max_row + 1)
    )
    assert "ERROR" in texto_resumen  # el archivo roto queda avisado, no oculto


# ------------------------------------------------------------- modo hojas


def test_hojas_una_por_archivo(tmp_path):
    a = _xlsx(tmp_path / "enero.xlsx", [["H1", "H2"], [1, FECHA]])
    b = _xlsx(tmp_path / "febrero.xlsx", [["H1", "H2"], [2, FECHA]])
    salida = str(tmp_path / "unido.xlsx")
    excel_tools.unir([a, b], salida, modo="hojas", log=_silencio)

    wb = openpyxl.load_workbook(salida, data_only=True)
    assert wb.sheetnames == ["enero", "febrero"]
    assert wb["enero"].cell(2, 1).value == 1
    assert hasattr(wb["febrero"].cell(2, 2).value, "year")


def test_hojas_nombres_largos_y_repetidos(tmp_path):
    nombre_largo = "REPORTE_DE_CARTERA_MENSUAL_CORTE_JUNIO_2026"
    carpeta1 = tmp_path / "c1"
    carpeta2 = tmp_path / "c2"
    carpeta1.mkdir()
    carpeta2.mkdir()
    a = _xlsx(carpeta1 / ("%s.xlsx" % nombre_largo), [["H"], [1]])
    b = _xlsx(carpeta2 / ("%s.xlsx" % nombre_largo), [["H"], [2]])
    salida = str(tmp_path / "unido.xlsx")
    excel_tools.unir([a, b], salida, modo="hojas", log=_silencio)

    wb = openpyxl.load_workbook(salida)
    assert len(wb.sheetnames) == 2
    assert all(len(n) <= 31 for n in wb.sheetnames)
    assert len(set(wb.sheetnames)) == 2  # sin nombres pisados


# ------------------------------------------------------------- errores claros


def test_sin_entradas_falla_claro(tmp_path):
    with pytest.raises(ValueError, match="No se encontraron"):
        excel_tools.unir([str(tmp_path / "nada")], str(tmp_path / "out.xlsx"), log=_silencio)


def test_modo_desconocido_falla_claro(tmp_path):
    a = _xlsx(tmp_path / "a.xlsx", [["H"], [1]])
    with pytest.raises(ValueError, match="Modo desconocido"):
        excel_tools.unir([a], str(tmp_path / "out.xlsx"), modo="magia", log=_silencio)
