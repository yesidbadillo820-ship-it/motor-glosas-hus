"""Tests del organizador de objeciones de SAVIA SALUD
(tools/organizar_objeciones_savia.py).

Cubre: normalización de factura, derivación del código de objeción (corto /
completo / mapa), extracción por texto (cantidad, valor unitario, servicio),
limpieza de la observación, y el pipeline lectura→escritura end-to-end contra
un Excel del Dispensario sintético con el mismo layout que
OBJECIONES_DISPENSARIO_HUS*.xlsx.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import organizar_objeciones_savia as org  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


# ─── Layout real del export del Dispensario ──────────────────────────────────

_HEADERS = [
    "CDCONSEC",
    "CDFECDOC",
    "CRNCXC",
    "CROFECOBJ",
    "CROREFERE",
    "CROOBSERV",
    "CROCLAOBJ",
    "CRNCLAOBJ",
    "GENUSUARIO4",
    "CRNCONOBJ",
    "SLNSERPRO",
    "IDRIPS",
    "CTNCENCOS",
    "CROVALOBJ",
    "CRDOBSERV",
    "CROTIPOBJ",
]


def _fila(factura, concepto, cod_serv, valor, texto):
    """Arma una fila con los 16 campos del Dispensario en su posición real."""
    r = [None] * 16
    r[2] = factura
    r[9] = concepto
    r[10] = cod_serv
    r[13] = valor
    r[14] = texto
    return r


def _crear_export(ruta: Path, filas: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "OBJECIONES"
    ws.append(_HEADERS)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


# ─── factura_corta ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("HUS0000530265", "HUS530265"),
        ("HUS0000409621", "HUS409621"),
        ("HUS443697", "HUS443697"),
        ("hus0000123", "HUS123"),
        ("", ""),
        (None, ""),
        ("SINPATRON", "SINPATRON"),  # sin dígitos → tal cual
    ],
)
def test_factura_corta(entrada, esperado):
    assert org.factura_corta(entrada) == esperado


# ─── codigo_savia ────────────────────────────────────────────────────────────


def test_codigo_savia_corto_toma_4_primeros():
    assert org.codigo_savia("CL0801", "corto") == "CL08"
    assert org.codigo_savia("TA0801", "corto") == "TA08"
    assert org.codigo_savia("SO0801", "corto") == "SO08"
    assert org.codigo_savia("CL0301", "corto") == "CL03"


def test_codigo_savia_completo_deja_tal_cual():
    assert org.codigo_savia("CL0801", "completo") == "CL0801"


def test_codigo_savia_mapa_tiene_prioridad():
    mapa = {"CL0801": "CL06"}
    assert org.codigo_savia("CL0801", "corto", mapa) == "CL06"
    # El mapa se aplica incluso en modo completo.
    assert org.codigo_savia("CL0801", "completo", mapa) == "CL06"
    # Un código fuera del mapa sigue la regla normal.
    assert org.codigo_savia("TA0801", "corto", mapa) == "TA08"


def test_codigo_savia_tolera_espacios_y_minusculas():
    assert org.codigo_savia("  cl0801 ", "corto") == "CL08"


# ─── extracción por texto ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("SE FACTURA UNA UNIDAD POR VALOR DE 3700 PESOS", 1),
        ("SE FACTURAN DOS UNIDADES POR VALOR DE 7400 PESOS", 2),
        ("SE FACTURAN TRES UNIDADES", 3),
        ("SE FACTURA 5 UNIDADES", 5),
        ("sin patron reconocible", 1),  # default
        ("", 1),
    ],
)
def test_extraer_cantidad(texto, esperado):
    assert org.extraer_cantidad(texto) == esperado


def test_extraer_valor_unitario_desde_texto():
    # "POR VALOR DE 93400" es el facturado; la glosa (7600) es parcial.
    texto = "SE FACTURA UNA UNIDAD POR VALOR DE 93400 PESOS. VALOR A OBJETAR 7600 PESOS."
    assert org.extraer_valor_unitario(texto, valor_glosa=7600, cantidad=1) == 93400


def test_extraer_valor_unitario_multiunidad_divide():
    texto = "SE FACTURAN DOS UNIDADES POR VALOR DE 7400 PESOS"
    assert org.extraer_valor_unitario(texto, valor_glosa=7400, cantidad=2) == 3700


def test_extraer_valor_unitario_fallback_a_glosa():
    # Sin "POR VALOR DE": objeción de línea completa → unitario = glosa/cantidad.
    assert org.extraer_valor_unitario("texto sin valor", valor_glosa=5000, cantidad=1) == 5000
    assert org.extraer_valor_unitario("texto sin valor", valor_glosa=5000, cantidad=2) == 2500


def test_extraer_servicio_desde_se_glosa_codigo():
    texto = (
        "CL0801 CALIDAD-APOYO DIAGNÓSTICO - SE GLOSA CODIGO 908337H RELACION "
        "LACTATO PIRUVATO. SE FACTURA UNA UNIDAD POR VALOR DE 458974 PESOS."
    )
    assert org.extraer_servicio(texto, "908337H", "CL0801") == "RELACION LACTATO PIRUVATO"


def test_extraer_servicio_fallback_concepto_encabezado():
    # Estancia: no trae código de servicio → usa el nombre del concepto.
    texto = (
        "CL0101 CALIDAD-ESTANCIA U OBSERVACIÓN DE URGENCIAS EL CARGO POR "
        "ESTANCIA NO ES PERTINENTE: SE GLOSA ESTANCIA POR INOPORTUNIDAD."
    )
    assert org.extraer_servicio(texto, "", "CL0101") == "ESTANCIA U OBSERVACIÓN DE URGENCIAS"


def test_extraer_servicio_vacio_si_no_hay_pista():
    assert org.extraer_servicio("texto sin estructura", "", "XX9999") == ""


# ─── limpiar_observacion ─────────────────────────────────────────────────────


def test_limpiar_observacion_quita_valor_pegado():
    t = "VALOR A OBJETAR 3700 PESOS.$3700"
    assert org.limpiar_observacion(t) == "VALOR A OBJETAR 3700 PESOS."


def test_limpiar_observacion_encabezado_opcional():
    t = "CL0801 CALIDAD-APOYO DIAGNÓSTICO - LOS CARGOS...$100"
    # Sin flag: conserva el código.
    assert org.limpiar_observacion(t).startswith("CL0801 CALIDAD-APOYO")
    # Con flag: quita sólo el token de código del inicio.
    limpio = org.limpiar_observacion(t, limpiar_encabezado=True)
    assert limpio.startswith("CALIDAD-APOYO DIAGNÓSTICO")
    assert "$100" not in limpio


def test_limpiar_observacion_normaliza_espacios():
    assert org.limpiar_observacion("  hola   mundo \n ") == "hola mundo"


# ─── _num ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        (622967, 622967),
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


# ─── Pipeline lectura → escritura end-to-end ─────────────────────────────────


def test_leer_objeciones_mapea_columnas_por_nombre(tmp_path):
    ruta = _crear_export(
        tmp_path / "OBJECIONES_DISPENSARIO_HUS0000530265.xlsx",
        [
            _fila(
                "HUS0000530265",
                "CL0801",
                "908337H",
                458974,
                "CL0801 CALIDAD-APOYO DIAGNÓSTICO - SE GLOSA CODIGO 908337H RELACION "
                "LACTATO PIRUVATO. SE FACTURA UNA UNIDAD POR VALOR DE 458974 PESOS.$458974",
            ),
        ],
    )
    objs = org.leer_objeciones(
        ruta,
        modo_codigo="corto",
        mapa_codigos=None,
        limpiar_encabezado=False,
        normalizar_factura=True,
    )
    assert len(objs) == 1
    o = objs[0]
    assert o["Numero_factura"] == "HUS530265"
    assert o["Cod_Servicio"] == "908337H"
    assert o["Servicio"] == "RELACION LACTATO PIRUVATO"
    assert o["Cantidad_Servicio"] == 1
    assert o["Valor_Unitario"] == 458974
    assert o["Valor_Glosa"] == 458974
    assert o["Motivo_Esp_Glosa_Valor_A"] == "CL08"
    assert o["Observacion_Glosa_A"].endswith("458974 PESOS.")
    assert "$458974" not in o["Observacion_Glosa_A"]


def test_leer_objeciones_ignora_filas_vacias(tmp_path):
    ruta = _crear_export(
        tmp_path / "x.xlsx",
        [
            _fila("HUS0000530265", "CL0801", "908337H", 458974, "texto"),
            _fila(None, None, None, None, None),  # fila basura
        ],
    )
    objs = org.leer_objeciones(
        ruta,
        modo_codigo="corto",
        mapa_codigos=None,
        limpiar_encabezado=False,
        normalizar_factura=True,
    )
    assert len(objs) == 1


def test_escribir_savia_headers_y_valores(tmp_path):
    objs = [
        {
            "Numero_factura": "HUS530265",
            "Cod_Servicio": "21519H",
            "Servicio": "LOCALIZACION",
            "Cantidad_Servicio": 1,
            "Valor_Unitario": 622967,
            "Valor_Glosa": 622967,
            "Motivo_Esp_Glosa_Valor_A": "CL03",
            "Observacion_Glosa_A": "texto",
        }
    ]
    salida = tmp_path / "out" / "SAVIA.xlsx"
    org.escribir_savia(objs, salida)
    assert salida.is_file()  # crea la carpeta padre

    ws = openpyxl.load_workbook(str(salida), data_only=True).active
    filas = list(ws.iter_rows(values_only=True))
    assert list(filas[0]) == [e for e, _ in org.ENCABEZADOS_SAVIA]
    assert filas[1][0] == "HUS530265"
    assert filas[1][6] == "CL03"


def test_cli_end_to_end(tmp_path, capsys):
    carpeta = tmp_path / "lote"
    carpeta.mkdir()
    _crear_export(
        carpeta / "OBJECIONES_DISPENSARIO_HUS0000530265.xlsx",
        [
            _fila(
                "HUS0000530265",
                "CL0801",
                "908337H",
                458974,
                "CL0801 CALIDAD - SE GLOSA CODIGO 908337H RELACION LACTATO PIRUVATO. "
                "SE FACTURA UNA UNIDAD POR VALOR DE 458974 PESOS.$458974",
            ),
            _fila(
                "HUS0000530265",
                "TA0801",
                "890701",
                7600,
                "TA0801 TARIFAS - SE GLOSA CODIGO 890701 CONSULTA. SE FACTURA UNA "
                "UNIDAD POR VALOR DE 93400 PESOS. VALOR A OBJETAR 7600 PESOS.$7600",
            ),
        ],
    )
    salida = tmp_path / "SAVIA_organizado.xlsx"
    rc = org.main(["--entrada", str(carpeta), "--salida", str(salida)])
    assert rc == 0
    assert salida.is_file()

    ws = openpyxl.load_workbook(str(salida), data_only=True).active
    filas = list(ws.iter_rows(values_only=True))[1:]
    assert len(filas) == 2
    codigos = {r[6] for r in filas}
    assert codigos == {"CL08", "TA08"}
    # La glosa parcial de tarifa conserva unitario≠glosa.
    ta = next(r for r in filas if r[6] == "TA08")
    assert ta[4] == 93400  # Valor_Unitario (facturado)
    assert ta[5] == 7600  # Valor_Glosa (objetado)


def test_cli_sin_archivos_valida(tmp_path):
    vacio = tmp_path / "vacia"
    vacio.mkdir()
    rc = org.main(["--entrada", str(vacio), "--salida", str(tmp_path / "out.xlsx")])
    assert rc == 1
