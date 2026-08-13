"""Tests del organizador de objeciones de FAMISANAR
(tools/organizar_objeciones_famisanar.py).

El tool convierte el export de FAMISANAR (4 columnas: NRO_FACTURA,
CODIGO_DEVOLUCION, VALOR DEVOLUCION, OBSERVACION) al formato de trabajo de 16
columnas (hoja OBJECIONES). La particularidad: el código del servicio viene
EMBEBIDO en el texto de la observación ("… CÓDIGO   903867 …") y el tool lo
extrae para SLNSERPRO. Cubre: extracción del código, factura corta→larga,
código de objeción, CRDOBSERV, CDCONSEC por factura, CROTIPOBJ, formatos de
celda y CLI end-to-end.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_objeciones_famisanar as org  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


_HEADERS = ["NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"]

_FECHA = dt.datetime(2026, 8, 13)

# Textos con el formato REAL de FAMISANAR (recortados).
OBS_COBERTURA = (
    "Los medicamentos o APME relacionados en los soportes de cobro no están "
    "incluidos en la respectiva cobertura  SERVICIO SIN COBERTURA    LOSARTAN "
    "(WIN) TABLETA POR 50 MG   CÓDIGO   U19965499-11 VALOR UNITARIO FACTURADO "
    "POR IPS     $        200"
)
OBS_TARIFA = (
    "Los cargos por apoyo diagnóstico que vienen relacionados o justificados "
    "en los soportes de cobro presentan diferencias con los valores pactados "
    "o establecidos por la norma  SE REALIZA OBJECIÓN POR MAYOR VALOR COBRADO "
    "DE ACUERDO A TARIFA CONTRATADA CON EPS FAMISANAR PARA EL SERVICIO "
    "TRANSAMINASA GLUTAMICO OXALACETICA [ASPARTATO AMINO TRANSFERASA]   "
    "CÓDIGO   903867 SE RECONOCE LO AUTORIZADO; SE OBJETA DIFERENCIA DE    "
    "$ 207100   DE   1   UNIDAD(ES)"
)
OBS_AUD_EXTRA = "AUD EXTRA - AUD EXTRA NO JUSTIFICADO EN PARTO. SIN REPORTE"
OBS_CON_PREFIJO = (
    "CO0601  Los dispositivos médicos que vienen relacionados o justificados "
    "en los soportes de cobro no están incluidos en la respectiva cobertura  "
    "SE REALIZA OBJECIÓN DE    3   CANT.   DE   ELECTRODO PARA MONITOREO "
    "ADULTO    CÓDIGO   91017424        A UN VALOR UNITARIO FACTURADO"
)


def _crear_famisanar(ruta: Path, filas: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DEVYGLOSAS0571393_900006037_202"
    ws.append(_HEADERS)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


# ─── extraer_cod_servicio ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "texto,esperado",
    [
        (OBS_COBERTURA, "U19965499-11"),
        (OBS_TARIFA, "903867"),
        (OBS_CON_PREFIJO, "91017424"),
        ("… CÓDIGO   P32606-02 VALOR …", "P32606-02"),
        ("… CODIGO 91017235 VALOR …", "91017235"),  # sin tilde también
        (OBS_AUD_EXTRA, ""),  # sin código → vacío
        ("", ""),
    ],
)
def test_extraer_cod_servicio(texto, esperado):
    assert org.extraer_cod_servicio(texto) == esperado


# ─── factura_larga ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("HUS532670", "HUS0000532670"),
        ("HUS0000532670", "HUS0000532670"),  # idempotente
        ("hus525618", "HUS0000525618"),
        ("", ""),
        (None, ""),
    ],
)
def test_factura_larga(entrada, esperado):
    assert org.factura_larga(entrada) == esperado


# ─── codigo_objecion ─────────────────────────────────────────────────────────


def test_codigo_objecion_seis_chars_tal_cual():
    # FAMISANAR ya entrega 6 caracteres: no se toca.
    assert org.codigo_objecion("CL0801") == "CL0801"
    assert org.codigo_objecion("FA0705") == "FA0705"


def test_codigo_objecion_completa_cuatro_chars():
    assert org.codigo_objecion("TA08") == "TA0801"


def test_codigo_objecion_mapa_gana():
    assert org.codigo_objecion("CO0701", mapa={"CO0701": "CO0799"}) == "CO0799"


# ─── construir_crdobserv ─────────────────────────────────────────────────────


def test_crdobserv_formato():
    out = org.construir_crdobserv("CO0701", OBS_COBERTURA, 200)
    assert out.startswith("CO0701 Los medicamentos")
    assert out.endswith("$200")


def test_crdobserv_no_duplica_codigo_si_ya_viene():
    out = org.construir_crdobserv("CO0601", OBS_CON_PREFIJO, 2400)
    assert out.startswith("CO0601 Los dispositivos")  # una sola vez
    assert not out.startswith("CO0601 CO0601")


def test_crdobserv_dedup_solo_si_el_monto_es_el_mismo():
    # Monto final IGUAL al valor de la objeción → duplicado genuino, se quita.
    assert org.construir_crdobserv("CO0701", "texto $        200", 200) == "CO0701 texto$200"
    # Monto final DISTINTO (valor unitario facturado) → se CONSERVA: es
    # información real del texto, no un duplicado (hallazgo de la revisión:
    # 18/37 filas del archivo real perdían el unitario).
    out = org.construir_crdobserv(
        "TA0801", "VALOR UNITARIO FACTURADO POR IPS     $    244,800", 207100
    )
    assert out == "TA0801 VALOR UNITARIO FACTURADO POR IPS $ 244,800$207100"


def test_crdobserv_normaliza_espacios_multiples():
    # Los exports de FAMISANAR traen corridas largas de espacios: se colapsan
    # a uno (comportamiento intencional, documentado en el docstring).
    out = org.construir_crdobserv("CO0701", "texto   con    espacios", 500)
    assert out == "CO0701 texto con espacios$500"


# ─── crotipobj_factura ───────────────────────────────────────────────────────


def test_crotipobj():
    assert org.crotipobj_factura({"TA", "CO", "FA"}) == 0
    assert org.crotipobj_factura({"CL"}) == 1
    assert org.crotipobj_factura({"CL", "CO", "TA"}) == 2


# ─── construir_registros (pipeline) ──────────────────────────────────────────


def test_construir_registros_extrae_y_mapea(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "FAMISANAR.xlsx",
        [
            ["HUS532670", "CL0801", 279900, OBS_AUD_EXTRA],
            ["HUS532670", "CO0701", 200, OBS_COBERTURA],
            ["HUS525618", "TA0801", 207100, OBS_TARIFA],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    assert len(regs) == 3
    assert list(regs[0].keys()) == list(org.COLUMNAS_DISPENSARIO)

    # AUD EXTRA: sin código de servicio.
    assert regs[0]["CRNCXC"] == "HUS0000532670"
    assert regs[0]["SLNSERPRO"] is None
    assert regs[0]["CRNCONOBJ"] == "CL0801"
    assert regs[0]["CRDOBSERV"] == f"CL0801 {OBS_AUD_EXTRA}$279900"

    # Cobertura: código extraído del texto.
    assert regs[1]["SLNSERPRO"] == "U19965499-11"
    assert regs[1]["CROVALOBJ"] == 200

    # Tarifa: código CUPS extraído.
    assert regs[2]["SLNSERPRO"] == "903867"

    # CDCONSEC por factura (texto): 532670 aparece primero → 1; 525618 → 2.
    assert [r["CDCONSEC"] for r in regs] == ["1", "1", "2"]

    # CROTIPOBJ: 532670 mezcla CL+CO → 2; 525618 solo TA → 0.
    assert regs[0]["CROTIPOBJ"] == 2
    assert regs[1]["CROTIPOBJ"] == 2
    assert regs[2]["CROTIPOBJ"] == 0

    # Tipos y constantes.
    assert regs[0]["GENUSUARIO4"] == "999"
    assert regs[0]["CROCLAOBJ"] == 0
    assert regs[0]["CDFECDOC"] == _FECHA


def test_construir_registros_ignora_filas_vacias(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "F.xlsx",
        [
            ["HUS532670", "CO0701", 200, OBS_COBERTURA],
            [None, None, None, None],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    assert len(regs) == 1


# ─── escritura y CLI ─────────────────────────────────────────────────────────


def test_cli_por_factura_y_formatos(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "FAMISANAR.xlsx",
        [
            ["HUS532670", "CO0701", 200, OBS_COBERTURA],
            ["HUS525618", "TA0801", 207100, OBS_TARIFA],
        ],
    )
    salida = tmp_path / "out"
    rc = org.main(["--entrada", str(ruta), "--salida", str(salida), "--fecha", "2026-08-13"])
    assert rc == 0
    files = sorted(p.name for p in salida.glob("*.xlsx"))
    assert files == [
        "OBJECIONES_FAMISANAR_HUS0000525618.xlsx",
        "OBJECIONES_FAMISANAR_HUS0000532670.xlsx",
    ]
    ws = openpyxl.load_workbook(str(salida / files[0])).active
    assert ws.title == "OBJECIONES"
    headers = [ws.cell(row=1, column=i).value for i in range(1, 17)]
    assert headers == list(org.COLUMNAS_DISPENSARIO)
    # Standalone: CDCONSEC reinicia en '1'.
    assert ws.cell(row=2, column=1).value == "1"
    # Formatos del archivo real (mismos que fija el test hermano de SAVIA).
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
    # Columnas vacías del formato quedan en None.
    vals = {
        nombre: ws.cell(row=2, column=i).value
        for i, nombre in enumerate(org.COLUMNAS_DISPENSARIO, start=1)
    }
    for vacia in ("CROREFERE", "CROOBSERV", "CRNCLAOBJ", "IDRIPS", "CTNCENCOS"):
        assert vals[vacia] is None


def test_escribir_por_factura_no_muta_los_registros(tmp_path):
    # Generar por-factura y DESPUÉS el consolidado desde la misma lista debe
    # conservar el 1,2,3… por factura (hallazgo de la revisión adversarial:
    # antes escribir_por_factura pisaba CDCONSEC en los dicts compartidos).
    ruta = _crear_famisanar(
        tmp_path / "F.xlsx",
        [
            ["HUS532670", "CO0701", 200, OBS_COBERTURA],
            ["HUS525618", "TA0801", 207100, OBS_TARIFA],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    org.escribir_por_factura(regs, tmp_path / "out")
    assert [r["CDCONSEC"] for r in regs] == ["1", "2"]  # intactos
    salida = tmp_path / "todo.xlsx"
    org.escribir_consolidado(regs, salida)
    ws = openpyxl.load_workbook(str(salida), data_only=True).active
    assert [f[0] for f in list(ws.iter_rows(values_only=True))[1:]] == ["1", "2"]


def test_cli_consolidado(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "FAMISANAR.xlsx",
        [
            ["HUS532670", "CO0701", 200, OBS_COBERTURA],
            ["HUS532670", "CL0801", 279900, OBS_AUD_EXTRA],
            ["HUS525618", "TA0801", 207100, OBS_TARIFA],
        ],
    )
    salida = tmp_path / "todo.xlsx"
    rc = org.main(["--entrada", str(ruta), "--salida", str(salida), "--consolidado"])
    assert rc == 0
    ws = openpyxl.load_workbook(str(salida), data_only=True).active
    filas = list(ws.iter_rows(values_only=True))[1:]
    assert len(filas) == 3
    assert [f[0] for f in filas] == ["1", "1", "2"]  # CDCONSEC por factura


def test_cli_entrada_inexistente(tmp_path):
    rc = org.main(["--entrada", str(tmp_path / "no.xlsx"), "--salida", str(tmp_path / "o")])
    assert rc == 1
