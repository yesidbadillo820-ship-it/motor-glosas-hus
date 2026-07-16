"""Tests del organizador de objeciones de SAVIA SALUD
(tools/organizar_objeciones_savia.py).

El tool convierte el Excel de glosas de SAVIA (8 columnas) al formato del
Dispensario (16 columnas, hoja OBJECIONES), un archivo por factura. Cubre:
normalización de factura (corta→larga), expansión del código (4→6 chars),
construcción de registros, escritura por factura / consolidada, parseo de fecha
y el CLI end-to-end.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_objeciones_savia as org  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


# ─── Layout de SAVIA (entrada) ───────────────────────────────────────────────

_HEADERS_SAVIA = [
    "Numero_factura",
    "Cod_Servicio",
    "Servicio",
    "Cantidad_Servicio",
    "Valor_Unitario",
    "Valor_Glosa",
    "Motivo_Esp_Glosa_Valor_A",
    "Observacion_Glosa_A",
]


def _crear_savia(ruta: Path, filas: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append(_HEADERS_SAVIA)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


_FECHA = dt.datetime(2026, 7, 16)


# ─── factura_larga ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("HUS443697", "HUS0000443697"),
        ("HUS503425", "HUS0000503425"),
        ("HUS0000443697", "HUS0000443697"),  # idempotente
        ("hus443697", "HUS0000443697"),
        ("", ""),
        (None, ""),
        ("SINPATRON", "SINPATRON"),
    ],
)
def test_factura_larga(entrada, esperado):
    assert org.factura_larga(entrada) == esperado


# ─── codigo_dispensario ──────────────────────────────────────────────────────


def test_codigo_dispensario_completa_4_a_6():
    assert org.codigo_dispensario("TA08") == "TA0801"
    assert org.codigo_dispensario("CL07") == "CL0701"
    assert org.codigo_dispensario("SO61") == "SO6101"


def test_codigo_dispensario_sufijo_configurable():
    assert org.codigo_dispensario("TA08", sufijo="05") == "TA0805"


def test_codigo_dispensario_ya_de_6_no_cambia():
    assert org.codigo_dispensario("TA0801") == "TA0801"


def test_codigo_dispensario_mapa_tiene_prioridad():
    mapa = {"TA08": "TA0899"}
    assert org.codigo_dispensario("TA08", mapa=mapa) == "TA0899"
    assert org.codigo_dispensario("CL07", mapa=mapa) == "CL0701"


def test_codigo_dispensario_tolera_espacios_minusculas():
    assert org.codigo_dispensario("  ta08 ") == "TA0801"


# ─── _num ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (7603, 7603),
        (3700.0, 3700),
        ("$1.234", 1234),
        ("1,234", 1234),
        (None, 0),
        ("", 0),
        ("abc", 0),
    ],
)
def test_num(entrada, esperado):
    assert org._num(entrada) == esperado


# ─── _parse_fecha ────────────────────────────────────────────────────────────


def test_parse_fecha_valida():
    assert org._parse_fecha("2026-07-10") == dt.datetime(2026, 7, 10)


def test_parse_fecha_default_hoy():
    f = org._parse_fecha(None)
    hoy = dt.date.today()
    assert (f.year, f.month, f.day) == (hoy.year, hoy.month, hoy.day)


def test_parse_fecha_invalida_sale(capsys):
    with pytest.raises(SystemExit):
        org._parse_fecha("10/07/2026")


# ─── construir_registros ─────────────────────────────────────────────────────


def test_construir_registros_mapea_al_layout_dispensario(tmp_path):
    ruta = _crear_savia(
        tmp_path / "SAVIA.xlsx",
        [
            ["HUS443697", "890701", "CONSULTA", 1, 93400, 7603, "TA02", "Se objeta mayor valor..."],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    assert len(regs) == 1
    reg = regs[0]
    # Todas las 16 columnas del Dispensario presentes y en su lugar.
    assert list(reg.keys()) == list(org.COLUMNAS_DISPENSARIO)
    assert reg["CRNCXC"] == "HUS0000443697"
    assert reg["CRNCONOBJ"] == "TA0201"
    assert reg["SLNSERPRO"] == "890701"
    assert reg["CROVALOBJ"] == 7603
    assert reg["CRDOBSERV"] == "Se objeta mayor valor..."
    assert reg["CDCONSEC"] == 1
    assert reg["CROCLAOBJ"] == 0
    assert reg["GENUSUARIO4"] == 999
    assert reg["CROTIPOBJ"] == 0
    assert reg["CDFECDOC"] == _FECHA
    assert reg["CROFECOBJ"] == _FECHA
    # Columnas vacías del formato.
    for vacia in ("CROREFERE", "CROOBSERV", "CRNCLAOBJ", "IDRIPS", "CTNCENCOS"):
        assert reg[vacia] is None


def test_construir_registros_ignora_filas_vacias(tmp_path):
    ruta = _crear_savia(
        tmp_path / "SAVIA.xlsx",
        [
            ["HUS443697", "890701", "CONSULTA", 1, 93400, 7603, "TA02", "texto"],
            [None, None, None, None, None, None, None, None],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    assert len(regs) == 1


# ─── escritura ───────────────────────────────────────────────────────────────


def test_escribir_por_factura_un_archivo_por_factura(tmp_path):
    ruta = _crear_savia(
        tmp_path / "SAVIA.xlsx",
        [
            ["HUS443697", "890701", "CONSULTA", 1, 93400, 7603, "TA02", "a"],
            ["HUS503425", "902210", "HEMOGRAMA", 1, 39400, 3199, "TA08", "b"],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    generados = org.escribir_por_factura(regs, tmp_path / "out")
    nombres = sorted(p.name for p in generados)
    assert nombres == [
        "OBJECIONES_DISPENSARIO_HUS0000443697.xlsx",
        "OBJECIONES_DISPENSARIO_HUS0000503425.xlsx",
    ]
    # El archivo generado tiene la hoja OBJECIONES y los 16 encabezados exactos.
    ws = openpyxl.load_workbook(str(generados[0]), data_only=True).active
    assert ws.title == "OBJECIONES"
    headers = list(next(ws.iter_rows(values_only=True)))
    assert headers == list(org.COLUMNAS_DISPENSARIO)


def test_cli_end_to_end_por_factura(tmp_path):
    ruta = _crear_savia(
        tmp_path / "SAVIA_SALUD_8.03.xlsx",
        [
            ["HUS443697", "890701", "CONSULTA", 1, 93400, 7603, "TA02", "a"],
            ["HUS443697", "906841", "PROCALCITONINA", 1, 293100, 293100, "CL08", "b"],
            ["HUS503425", "902210", "HEMOGRAMA", 1, 39400, 3199, "TA08", "c"],
        ],
    )
    salida = tmp_path / "OBJECIONES_SAVIA"
    rc = org.main(["--entrada", str(ruta), "--salida", str(salida), "--fecha", "2026-07-16"])
    assert rc == 0
    files = sorted(p.name for p in salida.glob("*.xlsx"))
    assert files == [
        "OBJECIONES_DISPENSARIO_HUS0000443697.xlsx",
        "OBJECIONES_DISPENSARIO_HUS0000503425.xlsx",
    ]
    # La factura HUS443697 debe traer sus 2 objeciones.
    ws = openpyxl.load_workbook(
        str(salida / "OBJECIONES_DISPENSARIO_HUS0000443697.xlsx"), data_only=True
    ).active
    filas = list(ws.iter_rows(values_only=True))[1:]
    assert len(filas) == 2
    assert {f[9] for f in filas} == {"TA0201", "CL0801"}  # CRNCONOBJ expandido


def test_cli_consolidado(tmp_path):
    ruta = _crear_savia(
        tmp_path / "SAVIA.xlsx",
        [
            ["HUS443697", "890701", "CONSULTA", 1, 93400, 7603, "TA02", "a"],
            ["HUS503425", "902210", "HEMOGRAMA", 1, 39400, 3199, "TA08", "b"],
        ],
    )
    salida = tmp_path / "todo.xlsx"
    rc = org.main(["--entrada", str(ruta), "--salida", str(salida), "--consolidado"])
    assert rc == 0
    assert salida.is_file()
    ws = openpyxl.load_workbook(str(salida), data_only=True).active
    assert len(list(ws.iter_rows(values_only=True))) == 3  # header + 2


def test_cli_entrada_inexistente(tmp_path):
    rc = org.main(["--entrada", str(tmp_path / "no.xlsx"), "--salida", str(tmp_path / "o")])
    assert rc == 1
