"""Tests del organizador de objeciones de SALUD TOTAL
(tools/organizar_objeciones_saludtotal.py).

El tool convierte la notificación de glosas de SALUD TOTAL (6 columnas:
NumeroFac_, NombreServicio, CantidadFac, ValorGlosaTotalxServ, Observaciones,
CodMotvGlosaEspc) al formato de trabajo de 16 columnas (hoja OBJECIONES).
Particularidades cubiertas: factura sin prefijo (464306 → HUS0000464306),
SLNSERPRO vacío u homologado por NOMBRE con --maestro, reparación del
encoding dañado («Ã“» → «Ó»), CDCONSEC por factura y CROTIPOBJ 0/1/2.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_objeciones_saludtotal as org  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


_HEADERS = [
    "NumeroFac_",
    "NombreServicio",
    "CantidadFac",
    "ValorGlosaTotalxServ",
    "Observaciones",
    "CodMotvGlosaEspc",
]
_FECHA = dt.datetime(2026, 8, 20)


def _crear_saludtotal(ruta: Path, filas: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NotificacionGLS_Crt03January202"
    ws.append(_HEADERS)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


# ─── factura_larga (número pelado → HUS larga) ───────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (464306, "HUS0000464306"),  # número pelado (como llega de SALUD TOTAL)
        ("464306", "HUS0000464306"),
        ("HUS464306", "HUS0000464306"),  # ya con prefijo
        ("HUS0000464306", "HUS0000464306"),  # idempotente
        ("", ""),
        (None, ""),
    ],
)
def test_factura_larga(entrada, esperado):
    assert org.factura_larga(entrada) == esperado


def test_factura_larga_prefijo_configurable():
    assert org.factura_larga(464306, prefijo="hus") == "HUS0000464306"


# ─── reparar_texto (mojibake) ────────────────────────────────────────────────


def test_reparar_texto_mojibake():
    assert org.reparar_texto("TABLETA Ã“ CÃ\x81PSULA") == "TABLETA Ó CÁPSULA"


def test_reparar_texto_sano_no_se_toca():
    assert org.reparar_texto("TABLETA Ó CÁPSULA 500 MG") == "TABLETA Ó CÁPSULA 500 MG"
    assert org.reparar_texto("") == ""


# ─── construir_crdobserv ─────────────────────────────────────────────────────


def test_crdobserv_formato():
    out = org.construir_crdobserv("CL0801", "se objeta cobro de fosforo 3", 95082)
    assert out == "CL0801 se objeta cobro de fosforo 3$95082"


def test_crdobserv_dedup_solo_si_el_monto_es_el_mismo():
    assert org.construir_crdobserv("TA0601", "texto $ 500", 500) == "TA0601 texto$500"
    # Monto distinto (p. ej. unitario) se conserva.
    assert org.construir_crdobserv("TA0601", "texto $ 900", 500) == "TA0601 texto $ 900$500"


# ─── maestro (homologación por nombre) ───────────────────────────────────────


def test_norm_nombre():
    assert org._norm_nombre("  Bolsa RECOLEC. Orina—Adulto ") == "BOLSA RECOLEC ORINA ADULTO"


def test_cargar_maestro_desde_objeciones(tmp_path):
    # Forma 1: un OBJECIONES trabajado (código en SLNSERPRO + "(COD-NOMBRE)" en CRDOBSERV).
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(org.COLUMNAS_DISPENSARIO))
    fila = dict.fromkeys(org.COLUMNAS_DISPENSARIO)
    fila.update(
        SLNSERPRO="FMQ0159",
        CRDOBSERV="TA2901 MAYOR VALOR COBRADO EN (FMQ0159-BOLSA RECOLECTORA DE ORINA ADULTO)$18100",
    )
    ws.append([fila[c] for c in org.COLUMNAS_DISPENSARIO])
    ruta = tmp_path / "LOTE.xlsx"
    wb.save(str(ruta))
    mapa = org.cargar_maestro(ruta)
    assert mapa == {"BOLSA RECOLECTORA DE ORINA ADULTO": "FMQ0159"}


def test_cargar_maestro_listado_simple(tmp_path):
    # Forma 2: listado código | nombre.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["CODIGO", "NOMBRE"])
    ws.append(["FMQ0112", "CATETER INTRAVENOSO 18"])
    ruta = tmp_path / "maestro.xlsx"
    wb.save(str(ruta))
    assert org.cargar_maestro(ruta) == {"CATETER INTRAVENOSO 18": "FMQ0112"}


# ─── crotipobj_factura ───────────────────────────────────────────────────────


def test_crotipobj():
    assert org.crotipobj_factura({"TA", "FA", "SO"}) == 0
    assert org.crotipobj_factura({"CL"}) == 1
    assert org.crotipobj_factura({"CL", "TA"}) == 2


# ─── construir_registros (pipeline) ──────────────────────────────────────────


def test_construir_registros_mapea_y_numera(tmp_path):
    ruta = _crear_saludtotal(
        tmp_path / "ST.xlsx",
        [
            [464306, "FOSFORO EN SUERO", 13, 95082, "se objeta cobro de fosforo", "CL0801"],
            [464306, "CLORO", 16, 34560, "se objeta cobro de cloro", "TA0601"],
            [464511, "NITROGENO UREICO (BUN)", 23, 56810, "se objeta bun", "TA0601"],
        ],
    )
    regs = org.construir_registros(ruta, fecha=_FECHA, consecutivo=1)
    assert len(regs) == 3
    assert list(regs[0].keys()) == list(org.COLUMNAS_DISPENSARIO)
    assert regs[0]["CRNCXC"] == "HUS0000464306"
    assert regs[0]["CRNCONOBJ"] == "CL0801"
    assert regs[0]["CROVALOBJ"] == 95082
    assert regs[0]["CRDOBSERV"] == "CL0801 se objeta cobro de fosforo$95082"
    assert regs[0]["SLNSERPRO"] is None  # sin maestro: vacío
    # CDCONSEC por factura (texto) y tipos.
    assert [r["CDCONSEC"] for r in regs] == ["1", "1", "2"]
    assert regs[0]["GENUSUARIO4"] == "999"
    assert regs[0]["CDFECDOC"] == _FECHA
    # CROTIPOBJ: 464306 mezcla CL+TA → 2; 464511 solo TA → 0.
    assert regs[0]["CROTIPOBJ"] == 2
    assert regs[1]["CROTIPOBJ"] == 2
    assert regs[2]["CROTIPOBJ"] == 0


def test_construir_registros_con_maestro(tmp_path):
    ruta = _crear_saludtotal(
        tmp_path / "ST.xlsx",
        [
            [464306, "BOLSA RECOLEC ORINA ADULTO", 1, 18100, "se objeta", "TA0601"],
            [464306, "SERVICIO DESCONOCIDO XYZ", 1, 500, "se objeta", "TA0601"],
        ],
    )
    maestro = {"BOLSA RECOLEC ORINA ADULTO": "FMQ0159"}
    regs = org.construir_registros(ruta, fecha=_FECHA, consecutivo=1, maestro=maestro)
    assert regs[0]["SLNSERPRO"] == "FMQ0159"  # match exacto por nombre
    assert regs[1]["SLNSERPRO"] is None  # sin match: vacío, no se inventa


def test_construir_registros_ignora_filas_vacias(tmp_path):
    ruta = _crear_saludtotal(
        tmp_path / "ST.xlsx",
        [
            [464306, "CLORO", 16, 34560, "obs", "TA0601"],
            [None, None, None, None, None, None],
        ],
    )
    regs = org.construir_registros(ruta, fecha=_FECHA, consecutivo=1)
    assert len(regs) == 1


# ─── escritura y CLI ─────────────────────────────────────────────────────────


def test_cli_por_factura_y_formatos(tmp_path):
    ruta = _crear_saludtotal(
        tmp_path / "ST.xlsx",
        [
            [464306, "CLORO", 16, 34560, "obs a", "TA0601"],
            [464511, "BUN", 23, 56810, "obs b", "CL0801"],
        ],
    )
    salida = tmp_path / "out"
    rc = org.main(["--entrada", str(ruta), "--salida", str(salida), "--fecha", "2026-08-20"])
    assert rc == 0
    files = sorted(p.name for p in salida.glob("*.xlsx"))
    assert files == [
        "OBJECIONES_SALUDTOTAL_HUS0000464306.xlsx",
        "OBJECIONES_SALUDTOTAL_HUS0000464511.xlsx",
    ]
    ws = openpyxl.load_workbook(str(salida / files[0])).active
    assert ws.title == "OBJECIONES"
    assert [ws.cell(row=1, column=i).value for i in range(1, 17)] == list(org.COLUMNAS_DISPENSARIO)
    fmt = {
        nombre: ws.cell(row=2, column=i).number_format
        for i, nombre in enumerate(org.COLUMNAS_DISPENSARIO, start=1)
    }
    assert fmt["CDCONSEC"] == "@"
    assert fmt["CDFECDOC"] == "mm-dd-yy"
    assert fmt["CROFECOBJ"] == "mm-dd-yy"
    assert fmt["CRNCXC"] == "@"
    assert fmt["GENUSUARIO4"] == "@"
    assert fmt["CRDOBSERV"] == "@"
    assert fmt["CROTIPOBJ"] == "0"
    assert "#,##0" in fmt["CROVALOBJ"]
    # Standalone: CDCONSEC reinicia en '1'; vacías en None.
    assert ws.cell(row=2, column=1).value == "1"
    vals = {
        nombre: ws.cell(row=2, column=i).value
        for i, nombre in enumerate(org.COLUMNAS_DISPENSARIO, start=1)
    }
    for vacia in ("CROREFERE", "CROOBSERV", "CRNCLAOBJ", "IDRIPS", "CTNCENCOS"):
        assert vals[vacia] is None


def test_cli_consolidado_no_muta(tmp_path):
    ruta = _crear_saludtotal(
        tmp_path / "ST.xlsx",
        [
            [464306, "CLORO", 16, 34560, "obs a", "TA0601"],
            [464511, "BUN", 23, 56810, "obs b", "TA0601"],
        ],
    )
    regs = org.construir_registros(ruta, fecha=_FECHA, consecutivo=1)
    org.escribir_por_factura(regs, tmp_path / "out")
    assert [r["CDCONSEC"] for r in regs] == ["1", "2"]  # intactos
    salida = tmp_path / "todo.xlsx"
    org.escribir_consolidado(regs, salida)
    ws = openpyxl.load_workbook(str(salida), data_only=True).active
    assert [f[0] for f in list(ws.iter_rows(values_only=True))[1:]] == ["1", "2"]


def test_cli_entrada_inexistente(tmp_path):
    rc = org.main(["--entrada", str(tmp_path / "no.xlsx"), "--salida", str(tmp_path / "o")])
    assert rc == 1


class TestValorConCentavosNoSeInfla:
    """El lector único de pesos también protege este bot del ×100."""

    def test_no_multiplica_por_cien(self):
        assert org._num("1.365,50") == 1365

    def test_los_miles_siguen_leyendose_bien(self):
        assert org._num("$114.900") == 114900
        assert org._num(42800) == 42800
        assert org._num("") == 0
