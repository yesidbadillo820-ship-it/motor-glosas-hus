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


# ─── homologar_cod_servicio (FAMISANAR → HUS) ────────────────────────────────


@pytest.mark.parametrize(
    "cod,esperado,regla",
    [
        ("903867", "903867", "igual"),  # CUPS: tal cual
        ("890202", "890202", "igual"),
        ("U20162259-04", "20162259-04", "letra"),  # med: quitar letra FAMISANAR
        ("P32606-02", "32606-02", "letra"),
        ("U53560-05", "53560-05", "letra"),
        # Dispositivos con equivalencia FMQ fija (confirmadas contra LOTE_02).
        ("91017235", "FMQ0112", "mapa"),
        ("91012136", "FMQ0182-1", "mapa"),
        ("91017424", "FMQ0952", "mapa"),
        ("91017278", "FMQ0159", "mapa"),
        # Dispositivo desconocido: sin regla, tal cual.
        ("91099999", "91099999", "igual"),
        ("", "", "vacio"),
    ],
)
def test_homologar_cod_servicio(cod, esperado, regla):
    assert org.homologar_cod_servicio(cod) == (esperado, regla)


def test_homologar_mapa_gana_a_la_regla():
    mapa = {"91017235": "19945678-01", "U53560-05": "OTRO-99"}
    assert org.homologar_cod_servicio("91017235", mapa) == ("19945678-01", "mapa")
    # El mapa también le gana a la regla de la letra.
    assert org.homologar_cod_servicio("U53560-05", mapa) == ("OTRO-99", "mapa")


def test_construir_registros_homologa_por_default(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "F.xlsx",
        [
            ["HUS532670", "CO0701", 33600, "… METOCLOPRAMIDA CÓDIGO   U20162259-04 VALOR …"],
            ["HUS532670", "TA0801", 207100, OBS_TARIFA],
        ],
    )
    regs = org.construir_registros(
        ruta, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
    )
    assert regs[0]["SLNSERPRO"] == "20162259-04"  # letra U quitada
    assert regs[1]["SLNSERPRO"] == "903867"  # CUPS intacto


def test_construir_registros_sin_homologar(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "F.xlsx",
        [["HUS532670", "CO0701", 33600, "… CÓDIGO   U20162259-04 VALOR …"]],
    )
    regs = org.construir_registros(
        ruta,
        fecha=_FECHA,
        consecutivo=1,
        codigo_sufijo="01",
        mapa_codigos=None,
        homologar=False,
    )
    assert regs[0]["SLNSERPRO"] == "U20162259-04"  # tal cual FAMISANAR


def test_construir_registros_mapa_servicios(tmp_path):
    ruta = _crear_famisanar(
        tmp_path / "F.xlsx",
        [["HUS532670", "CO0601", 5800, "… CATETER CÓDIGO   91017235 VALOR …"]],
    )
    regs = org.construir_registros(
        ruta,
        fecha=_FECHA,
        consecutivo=1,
        codigo_sufijo="01",
        mapa_codigos=None,
        mapa_servicios={"91017235": "19999999-01"},
    )
    assert regs[0]["SLNSERPRO"] == "19999999-01"


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

    # Cobertura: código extraído del texto y homologado (letra U quitada).
    assert regs[1]["SLNSERPRO"] == "19965499-11"
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


# ─── Cruce contra los servicios facturados del DGH ───────────────────────────

_HEADERS_DGH = [
    "SERVICIOS DGH",
    "DESCRIPCION INSTITUCIONAL",
    "SLNSERPRO_CUPS",
    "DESCRIPCION CUPS",
    "CODIGO_MEDICAMENTO",
    "NOMBRE_MEDICAMENTO",
    "NOM_CENTRO_COSTO",
    "FACTURA",
    "CAT_SERVICIOS",
    "Vr_SERVICIO",
    "SALDO_FACT",
]

# Texto real: el código va PEGADO adelante del nombre y la etiqueta CÓDIGO
# queda vacía (por eso antes entraba la palabra "VALOR" a SLNSERPRO).
OBS_COD_ADELANTE = (
    "Los dispositivos médicos que vienen relacionados o justificados en los "
    "soportes de cobro no están incluidos en la respectiva cobertura  SERVICIO "
    "SIN COBERTURA    FMQ0113 CATETER INTRAVENOSO 20   CÓDIGO    VALOR UNITARIO "
    "FACTURADO POR IPS     $      5,800"
)
# FAMISANAR nombra los dispositivos con su propia nomenclatura (IUM).
OBS_IUM = (
    "Los dispositivos médicos que vienen relacionados o justificados en los "
    "soportes de cobro no están incluidos en la respectiva cobertura  SERVICIO "
    "SIN COBERTURA    LINEA INFUSION E INYECCION - JERINGA 1ML 25G x 16 mm   "
    "CÓDIGO   91022534 VALOR UNITARIO FACTURADO POR IPS     $      1,300"
)


def _crear_dgh(ruta: Path, filas: list[list]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DGDATATABLE"
    ws.append(_HEADERS_DGH)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


def _linea(codigo, descripcion, cant, valor, centro="URGENCIAS", cups="", cod_med=""):
    return org.LineaDgh(
        codigo=codigo,
        descripcion=descripcion,
        desc_cups="",
        nombre_med="",
        cups=cups,
        cod_med=cod_med,
        centro=centro,
        cant=cant,
        valor=valor,
    )


class TestLecturaDelTexto:
    def test_codigo_pegado_adelante_del_nombre(self):
        # La etiqueta CÓDIGO va vacía: el código está delante del nombre.
        assert org.extraer_cod_servicio(OBS_COD_ADELANTE) == ""  # "VALOR" ya no pasa
        assert org.codigo_servicio_del_texto(OBS_COD_ADELANTE) == "FMQ0113"

    def test_codigo_detras_de_la_etiqueta(self):
        assert org.codigo_servicio_del_texto(OBS_COBERTURA) == "U19965499-11"
        assert org.codigo_servicio_del_texto(OBS_TARIFA) == "903867"

    def test_descripcion_de_cada_patron(self):
        assert org.descripcion_del_texto(OBS_COD_ADELANTE) == "CATETER INTRAVENOSO 20"
        assert org.descripcion_del_texto(OBS_COBERTURA) == "LOSARTAN (WIN) TABLETA POR 50 MG"
        assert org.descripcion_del_texto(OBS_TARIFA).startswith("TRANSAMINASA GLUTAMICO")
        assert org.descripcion_del_texto(OBS_CON_PREFIJO) == "ELECTRODO PARA MONITOREO ADULTO"

    def test_valor_unitario_y_cantidad(self):
        assert org.valor_unitario_del_texto(OBS_COD_ADELANTE) == 5800
        assert org.valor_unitario_del_texto(OBS_TARIFA) == 0
        assert org.cantidad_del_texto(OBS_TARIFA) == 1

    def test_texto_vacio(self):
        assert org.codigo_servicio_del_texto("") == ""
        assert org.descripcion_del_texto("") == ""
        assert org.valor_unitario_del_texto("") == 0


class TestVariantesCodigo:
    def test_letra_que_antepone_famisanar(self):
        assert org.variantes_codigo("P32606-02") & org.variantes_codigo("32606-2")
        assert org.variantes_codigo("U211363-03") & org.variantes_codigo("211363-3")

    def test_h_que_agrega_el_dgh_al_cups(self):
        assert org.variantes_codigo("903437H") & org.variantes_codigo("903437")

    def test_codigos_distintos_no_se_cruzan(self):
        assert not (org.variantes_codigo("FMQ0113") & org.variantes_codigo("FMQ0115"))

    def test_vacio(self):
        assert org.variantes_codigo("") == set()
        assert org.variantes_codigo(None) == set()


class TestParecidoDescripcion:
    def test_numero_y_unidad_pegados(self):
        r = org.parecido_desc(
            org.norm_desc("LINEA INFUSION E INYECCION - JERINGA 1 ML CON AGUJA 27GA"),
            org.norm_desc("JERINGA DESECHABLE 1ML"),
        )
        assert r >= 0.55

    def test_sin_palabras_en_comun_no_se_parecen(self):
        r = org.parecido_desc(
            org.norm_desc("VITAMINA D3 CAP X 1.000 U.I"), org.norm_desc("JERINGA 1ML 25G")
        )
        assert r <= 0.30

    def test_formas_alternativas_del_nombre(self):
        formas = org.formas_descripcion("LINEA CIRUGIA GENERAL - CATETER PREMICATH 28G")
        assert "CATETER PREMICATH 28G" in formas


class TestResolverServicio:
    def test_codigo_y_valor_dan_confianza_alta(self):
        lineas = [_linea("32606-2", "SOLUCION LACTATO DE RINGER BOLSA X 500ML", 3, 12600)]
        obs = (
            "SERVICIO SIN COBERTURA   LACTATO DE RINGER (BXT) SOLUCION INYECTABLE "
            "BOLSA POR 500ML  CÓDIGO   P32606-02 VALOR UNITARIO FACTURADO POR IPS $ 4,200"
        )
        cruce = org.resolver_servicio("P32606-02", obs, 12600, lineas)
        assert cruce.confianza == "ALTA"
        assert cruce.linea.codigo == "32606-2"

    def test_valor_unico_identifica_aunque_el_nombre_sea_otro(self):
        lineas = [
            _linea("FMQ9001", "SET BABYFLOW NEONATAL", 1, 270400, "UCI PEDIATRICA"),
            _linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800),
        ]
        obs = (
            "SERVICIO SIN COBERTURA   LINEA RESPIRATORIA - KIT BABYFLOW MASCARA NASAL "
            "CÓDIGO   91018078 VALOR UNITARIO FACTURADO POR IPS $ 270,400"
        )
        cruce = org.resolver_servicio("91018078", obs, 270400, lineas)
        assert cruce.linea.codigo == "FMQ9001"
        assert cruce.linea.centro_costo == "UCI PEDIATRICA"
        assert "valor único en la factura" in cruce.motivos

    def test_valor_repetido_lo_desempata_el_nombre(self):
        lineas = [
            _linea("VIT-1", "VITAMINA D3 CAP X 1.000 U.I", 1, 1300),
            _linea("FMQ3616-1", "JERINGA 1ML + TAPON PARA DOSIS UNITARIA", 1, 1300),
        ]
        cruce = org.resolver_servicio("91022534", OBS_IUM, 1300, lineas)
        assert cruce.linea.codigo == "FMQ3616-1"

    def test_sin_datos_del_servicio_no_se_inventa(self):
        lineas = [_linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800)]
        cruce = org.resolver_servicio("", OBS_AUD_EXTRA, 4638000, lineas)
        assert cruce.linea is None
        assert cruce.confianza == "SIN CRUCE"
        assert "completar a mano" in cruce.aviso

    def test_factura_sin_servicios_en_el_export(self):
        cruce = org.resolver_servicio("FMQ0113", OBS_COD_ADELANTE, 5800, [])
        assert cruce.linea is None
        assert "no está en el export del DGH" in cruce.aviso

    def test_nombre_en_conflicto_cruza_pero_se_marca(self):
        # FAMISANAR busca el código en el catálogo CUPS y no en el del hospital:
        # 150101 es en el DGH una fórmula enteral, no una biopsia. El valor
        # confirma que es la misma línea.
        lineas = [_linea("150101", "ENSURE CLINICAL BOTELLA X 220 ml", 1, 16200)]
        obs = (
            "POS   BIOPSIA DE MUSCULO O TENDON EXTRAOCULAR CÓDIGO   150101DE   1   "
            "UNIDAD(ES), A UN VALOR FACTURADO POR LA IPS   16,200"
        )
        cruce = org.resolver_servicio("150101", obs, 16200, lineas)
        assert cruce.linea is not None
        assert cruce.confianza != "ALTA"
        assert "no coincide" in cruce.aviso

    def test_objeciones_repetidas_se_reparten_entre_renglones(self):
        lineas = [
            _linea("FMQ0177", "JERINGA DESECHABLES 5ML", 2, 1400),
            _linea("FMQ0177", "JERINGA DESECHABLES 5ML", 2, 1400),
        ]
        obs = (
            "SERVICIO SIN COBERTURA   FMQ0177 JERINGA DESECHABLES 5ML  CÓDIGO   "
            "VALOR UNITARIO FACTURADO POR IPS $ 700"
        )
        primero = org.resolver_servicio("FMQ0177", obs, 1400, lineas)
        segundo = org.resolver_servicio("FMQ0177", obs, 1400, lineas)
        assert primero.linea is not segundo.linea


class TestConstruirRegistrosConCruce:
    def _archivos(self, tmp_path):
        entrada = _crear_famisanar(
            tmp_path / "FAMISANAR.xlsx",
            [
                ["HUS549272", "CO0601", 5800, OBS_COD_ADELANTE],
                ["HUS549272", "CO0601", 1300, OBS_IUM],
                ["HUS549272", "CL0801", 279900, OBS_AUD_EXTRA],
            ],
        )
        dgh = _crear_dgh(
            tmp_path / "DGH.xlsx",
            [
                [
                    "FMQ0113",
                    "CATETER INTRAVENOSO 20",
                    "FMQ0113",
                    "CATETER INTRAVENOSO 20",
                    "",
                    "",
                    "URGENCIAS ADULTOS",
                    "HUS0000549272",
                    1,
                    5800,
                    100000,
                ],
                [
                    "FMQ3616-1",
                    "JERINGA 1ML + TAPON PARA DOSIS UNITARIA",
                    "FMQ3616-1",
                    "",
                    "",
                    "",
                    "SALA DE PARTOS",
                    "HUS0000549272",
                    1,
                    1300,
                    100000,
                ],
            ],
        )
        return entrada, dgh

    def test_slnserpro_queda_con_el_codigo_del_hospital(self, tmp_path):
        entrada, dgh = self._archivos(tmp_path)
        servicios = org.leer_servicios_dgh(dgh)
        trazas: list[dict] = []
        regs = org.construir_registros(
            entrada,
            fecha=_FECHA,
            consecutivo=1,
            codigo_sufijo="01",
            mapa_codigos=None,
            servicios_dgh=servicios,
            trazas=trazas,
        )
        assert regs[0]["SLNSERPRO"] == "FMQ0113"
        assert regs[0]["CTNCENCOS"] == "URGENCIAS ADULTOS"
        # El código IUM de FAMISANAR (91022534) queda con el del hospital.
        assert regs[1]["SLNSERPRO"] == "FMQ3616-1"
        assert regs[1]["CTNCENCOS"] == "SALA DE PARTOS"
        # AUD EXTRA sin servicio: no se inventa nada.
        assert regs[2]["SLNSERPRO"] is None
        assert regs[2]["CTNCENCOS"] is None
        assert trazas[2]["confianza"] == "SIN CRUCE"

    def test_los_registros_conservan_las_16_columnas(self, tmp_path):
        entrada, dgh = self._archivos(tmp_path)
        regs = org.construir_registros(
            entrada,
            fecha=_FECHA,
            consecutivo=1,
            codigo_sufijo="01",
            mapa_codigos=None,
            servicios_dgh=org.leer_servicios_dgh(dgh),
            trazas=[],
        )
        assert list(regs[0].keys()) == list(org.COLUMNAS_DISPENSARIO)

    def test_sin_export_del_dgh_se_comporta_como_antes(self, tmp_path):
        entrada, _ = self._archivos(tmp_path)
        regs = org.construir_registros(
            entrada, fecha=_FECHA, consecutivo=1, codigo_sufijo="01", mapa_codigos=None
        )
        assert regs[0]["CTNCENCOS"] is None
        assert regs[1]["SLNSERPRO"] == "91022534"  # el código de FAMISANAR, tal cual

    def test_export_del_dgh_que_no_lo_es(self, tmp_path):
        malo = _crear_famisanar(tmp_path / "otro.xlsx", [["HUS1", "CO0601", 100, "x"]])
        with pytest.raises(ValueError, match="export de servicios del DGH"):
            org.leer_servicios_dgh(malo)


class TestReporteCruce:
    def test_escribe_las_tres_hojas(self, tmp_path):
        trazas = [
            {
                "factura": "HUS0000549272",
                "codigo_objecion": "CO0601",
                "valor": 5800,
                "cod_famisanar": "FMQ0113",
                "desc_famisanar": "CATETER INTRAVENOSO 20",
                "unitario_famisanar": 5800,
                "cod_dgh": "FMQ0113",
                "servicio_dgh": "CATETER INTRAVENOSO 20",
                "unitario_dgh": 5800,
                "centro_costo": "URGENCIAS ADULTOS",
                "confianza": "ALTA",
                "motivos": "código, valor unitario",
                "puntaje": 8.0,
                "aviso": "",
                "observacion": OBS_COD_ADELANTE,
            },
            {
                "factura": "HUS0000549272",
                "codigo_objecion": "CL0801",
                "valor": 279900,
                "cod_famisanar": "",
                "desc_famisanar": "",
                "unitario_famisanar": 0,
                "cod_dgh": "",
                "servicio_dgh": "",
                "unitario_dgh": "",
                "centro_costo": "",
                "confianza": "SIN CRUCE",
                "motivos": "",
                "puntaje": 0.0,
                "aviso": "no se identificó el servicio: completar a mano",
                "observacion": OBS_AUD_EXTRA,
            },
        ]
        salida = tmp_path / "CRUCE.xlsx"
        org.escribir_reporte_cruce(trazas, salida)
        wb = openpyxl.load_workbook(str(salida))
        assert wb.sheetnames == ["CRUCE", "REVISAR", "RESUMEN"]
        assert wb["CRUCE"].max_row == 3
        assert wb["REVISAR"].max_row == 2  # sólo la que hay que revisar
        resumen = list(wb["RESUMEN"].iter_rows(min_row=2, values_only=True))
        assert resumen[0][0] == "HUS0000549272"
        assert resumen[0][1] == 2
        assert resumen[0][2] == 285700
        assert "Revisar" in resumen[0][7]
        assert resumen[-1][0] == "TOTAL"


class TestCliCruce:
    def test_end_to_end_con_export_del_dgh(self, tmp_path):
        entrada = _crear_famisanar(
            tmp_path / "FAMISANAR.xlsx", [["HUS549272", "CO0601", 5800, OBS_COD_ADELANTE]]
        )
        dgh = _crear_dgh(
            tmp_path / "DGH.xlsx",
            [
                [
                    "FMQ0113",
                    "CATETER INTRAVENOSO 20",
                    "FMQ0113",
                    "",
                    "",
                    "",
                    "URGENCIAS ADULTOS",
                    "HUS0000549272",
                    1,
                    5800,
                    100000,
                ]
            ],
        )
        salida = tmp_path / "OBJECIONES.xlsx"
        reporte = tmp_path / "CRUCE.xlsx"
        assert (
            org.main(
                [
                    "--entrada",
                    str(entrada),
                    "--servicios-dgh",
                    str(dgh),
                    "--salida",
                    str(salida),
                    "--consolidado",
                    "--reporte-cruce",
                    str(reporte),
                    "--fecha",
                    "2026-09-01",
                ]
            )
            == 0
        )
        wb = openpyxl.load_workbook(str(salida))
        ws = wb["OBJECIONES"]
        headers = [c.value for c in ws[1]]
        fila = dict(zip(headers, [c.value for c in ws[2]], strict=True))
        assert fila["SLNSERPRO"] == "FMQ0113"
        assert fila["CTNCENCOS"] == "URGENCIAS ADULTOS"
        assert reporte.is_file()

    def test_reporte_sin_export_del_dgh_avisa(self, tmp_path):
        entrada = _crear_famisanar(
            tmp_path / "FAMISANAR.xlsx", [["HUS549272", "CO0601", 5800, OBS_COD_ADELANTE]]
        )
        assert (
            org.main(
                [
                    "--entrada",
                    str(entrada),
                    "--salida",
                    str(tmp_path / "OBJECIONES.xlsx"),
                    "--consolidado",
                    "--reporte-cruce",
                    str(tmp_path / "CRUCE.xlsx"),
                ]
            )
            == 1
        )
