"""organizar_objeciones_famisanar.py — Arma las objeciones de FAMISANAR en el
formato de trabajo de 16 columnas (hoja OBJECIONES).

Toma el Excel de devoluciones/glosas que entrega FAMISANAR (export
"DEVYGLOSAS…": 4 columnas — NRO_FACTURA, CODIGO_DEVOLUCION, VALOR DEVOLUCION,
OBSERVACION) y lo convierte al mismo layout de 16 columnas que se usa para
SAVIA y el Dispensario:

    CDCONSEC | CDFECDOC | CRNCXC | CROFECOBJ | CROREFERE | CROOBSERV | CROCLAOBJ |
    CRNCLAOBJ | GENUSUARIO4 | CRNCONOBJ | SLNSERPRO | IDRIPS | CTNCENCOS |
    CROVALOBJ | CRDOBSERV | CROTIPOBJ

La particularidad de FAMISANAR: el Excel NO trae columna de código de servicio.
El código viene EMBEBIDO en el texto de la observación ("… CÓDIGO   903867 …",
"… CÓDIGO   U19965499-11 …"). Este bot lo EXTRAE del texto para llenar
SLNSERPRO. Las filas cortas tipo "AUD EXTRA - …" no traen código y quedan con
SLNSERPRO vacío (igual que las estancias en los archivos del Dispensario).

MAPEO DE CAMPOS (FAMISANAR → 16 columnas):
    CRNCXC       ← NRO_FACTURA          (HUS532670 → HUS0000532670, 10 dígitos)
    CRNCONOBJ    ← CODIGO_DEVOLUCION    (ya viene de 6: CL0801, CO0701, TA0801…)
    CTNCENCOS    ← SIEMPRE vacía (regla del área)
    SLNSERPRO    ← extraído del texto ("CÓDIGO <x>") y HOMOLOGADO al código HUS:
                   CUPS tal cual; medicamentos U/P → se quita la letra
                   (U20162259-04 → 20162259-04); dispositivos 9101xxxx → código
                   FMQ del HUS (equivalencias fijas confirmadas, ver
                   MAPA_SERVICIOS_DEFAULT); los no mapeados quedan tal cual +
                   aviso (completar con --mapa-servicios)
    CROVALOBJ    ← VALOR DEVOLUCION
    CRDOBSERV    ← "<CRNCONOBJ> <OBSERVACION>$<valor>" (formato de trabajo)
    CDFECDOC / CROFECOBJ ← --fecha (default: hoy), en FECHA CORTA
    CDCONSEC     ← consecutivo POR FACTURA (1-1-1 la 1ª, 2-2-2 la 2ª, …), texto
    CROTIPOBJ    ← por factura: solo TA/FA/SO/AU/CO→0, solo CL→1, mezcla con CL→2
    CROCLAOBJ=0, GENUSUARIO4='999' (texto)  |  resto de columnas vacías

Las 7 reglas del formato son las mismas del bot de SAVIA
(`organizar_objeciones_savia.py`) — verificadas contra archivos reales
(OBJECIONES_DISPENSARIO_* y OBJECIONES_EMSSANAR_*). Este tool es autocontenido
a propósito (patrón del repo: un archivo por bot, ejecutable suelto).

USO:
    py organizar_objeciones_famisanar.py \
        --entrada "FAMISANAR_11.35.1.xlsx" \
        --salida  "OBJECIONES_FAMISANAR"      # carpeta destino (o .xlsx con --consolidado)

INSTALACIÓN (una vez):
    py -m pip install openpyxl
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# Un solo lector de pesos para todos los bots (tools/_dinero.py): la copia
# local multiplicaba por cien los valores con centavos.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cruce_dgh import (  # noqa: E402
    Cruce,
    LineaDgh,
    escribir_reporte_cruce,
    factura_larga,
    leer_servicios_dgh,
    resolver_servicio,
    traza,
)
from _dinero import a_entero  # noqa: E402

logger = logging.getLogger("organizar_famisanar")


# ─── Formato de salida: layout de 16 columnas (hoja OBJECIONES) ──────────────

COLUMNAS_DISPENSARIO: tuple[str, ...] = (
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
)

# Constantes de la guía. CDCONSEC y GENUSUARIO4 van como TEXTO en los archivos
# reales; CROCLAOBJ/CROVALOBJ/CROTIPOBJ como número.
CDCONSEC_DEFAULT = 1
CROCLAOBJ_CONST = 0
GENUSUARIO4_CONST = "999"
CODIGO_SUFIJO_DEFAULT = "01"

# number_format por columna, copiado 1:1 de los archivos reales (EMSSANAR).
# 'mm-dd-yy' = fecha corta builtin de Excel (se ve dd/mm/yyyy según la config
# regional, sin horas); '@' = texto; CROVALOBJ con formato contable de miles.
FORMATOS_DISPENSARIO: dict[str, str] = {
    "CDCONSEC": "@",
    "CDFECDOC": "mm-dd-yy",
    "CRNCXC": "@",
    "CROFECOBJ": "mm-dd-yy",
    "CROREFERE": "@",
    "CROOBSERV": "@",
    "CROCLAOBJ": "General",
    "CRNCLAOBJ": "@",
    "GENUSUARIO4": "@",
    "CRNCONOBJ": "@",
    "SLNSERPRO": "@",
    "IDRIPS": "@",
    "CTNCENCOS": "@",
    "CROVALOBJ": '_-* #,##0_-;\\-* #,##0_-;_-* "-"_-;_-@_-',
    "CRDOBSERV": "@",
    "CROTIPOBJ": "0",
}


# ─── Lectura del Excel de FAMISANAR (4 columnas) ─────────────────────────────


def _norm_header(h: object) -> str:
    """Normaliza un encabezado: mayúsculas, sin tildes, sin espacios de más."""
    s = unicodedata.normalize("NFKD", str(h or "").strip().upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# Alias de las columnas del export de FAMISANAR (tolerante a variaciones).
COLUMNAS_FAMISANAR = {
    "factura": {"NRO_FACTURA", "NRO FACTURA", "NUMERO_FACTURA", "NUMERO FACTURA", "FACTURA"},
    "codigo_devolucion": {
        "CODIGO_DEVOLUCION",
        "CODIGO DEVOLUCION",
        "CODIGO_GLOSA",
        "CODIGO GLOSA",
        "COD DEVOLUCION",
    },
    "valor": {"VALOR DEVOLUCION", "VALOR_DEVOLUCION", "VALOR GLOSA", "VALOR_GLOSA", "VALOR"},
    "observacion": {"OBSERVACION", "OBSERVACIONES", "OBSERVACION GLOSA", "DETALLE"},
}
# Índices fijos de respaldo (layout de FAMISANAR_11.35.1.xlsx).
IDX_FALLBACK = {
    "factura": 0,
    "codigo_devolucion": 1,
    "valor": 2,
    "observacion": 3,
}


def _resolver_columnas(headers: list[str]) -> dict[str, int]:
    """Devuelve {clave: indice} mapeando por nombre de encabezado; si una
    columna no se reconoce por nombre, usa el índice fijo de respaldo."""
    norm = [_norm_header(h) for h in headers]
    idx: dict[str, int] = {}
    for clave, alias in COLUMNAS_FAMISANAR.items():
        encontrado = next((i for i, h in enumerate(norm) if h in alias), None)
        if encontrado is None:
            encontrado = IDX_FALLBACK[clave]
            logger.debug(
                f"  columna '{clave}' no reconocida por nombre; uso índice fijo {encontrado}"
            )
        idx[clave] = encontrado
    return idx


def _cell(row: tuple, idx: dict[str, int], clave: str) -> object:
    """Valor de la columna `clave` en `row`, o None si el índice se sale de rango."""
    i = idx[clave]
    return row[i] if i < len(row) else None


def _num(v: object) -> int:
    """Pesos enteros, con el lector único de `tools/_dinero.py` (regla
    colombiana: un separador de miles lleva tres dígitos detrás; uno o dos son
    decimales — así "1.365,50" es 1365 y no 136550)."""
    return a_entero(v)


# ─── Normalización de factura (corta → larga) ────────────────────────────────

# ─── Código de objeción ──────────────────────────────────────────────────────


def codigo_objecion(codigo: str, sufijo: str = CODIGO_SUFIJO_DEFAULT, mapa=None) -> str:
    """FAMISANAR ya entrega el código de 6 caracteres (CL0801, CO0701…): se
    deja tal cual. Red de seguridad: si viniera de 4 (grupo+concepto) se
    completa con el `sufijo`, y `mapa` (--mapa-codigos) fuerza equivalencias
    puntuales — misma semántica que el bot de SAVIA."""
    cod = (codigo or "").strip().upper()
    if mapa and cod in mapa:
        return mapa[cod]
    if re.fullmatch(r"[A-Z]{2}\d{2}", cod):
        return cod + sufijo
    return cod


# ─── Extracción del código de servicio desde la observación ──────────────────

# En los textos de FAMISANAR el código del servicio/insumo viene como
# "… CÓDIGO   903867 SE RECONOCE …" / "… CÓDIGO   U19965499-11 VALOR …".
# Acepta dígitos, letras y guiones (91017235, U19965499-11, P32606-02).
_RE_COD_SERVICIO = re.compile(r"C[OÓ]DIGO\s+([A-Za-z0-9][A-Za-z0-9.\-]*)", re.IGNORECASE)


def extraer_cod_servicio(observacion: str) -> str:
    """Extrae el código de servicio embebido en el texto de la objeción.
    Devuelve '' si el texto no trae código (p. ej. filas 'AUD EXTRA - …').

    Cuando FAMISANAR deja la etiqueta CÓDIGO vacía —"… CATETER INTRAVENOSO 20
    CÓDIGO    VALOR UNITARIO FACTURADO…"— lo que sigue es la frase siguiente,
    no un código: todo código de servicio trae al menos un dígito, así que sin
    dígitos se descarta (antes entraba la palabra VALOR a SLNSERPRO)."""
    m = _RE_COD_SERVICIO.search(observacion or "")
    if not m:
        return ""
    cod = m.group(1).strip(".-")
    return cod if any(c.isdigit() for c in cod) else ""


# ─── Homologación: código FAMISANAR → código HUS ─────────────────────────────

# Los códigos que FAMISANAR escribe en sus textos NO son (todos) los del HUS:
#   - CUPS de 6 dígitos (890202, 903867, 735301…): son el estándar nacional,
#     los mismos que usa el HUS → tal cual.
#   - Medicamentos con LETRA adelante (U20162259-04, P32606-02…): la letra es
#     de FAMISANAR; sin ella queda el código del HUS. Verificado contra los
#     archivos de trabajo: U20162259-04 → 20162259-04 (METOCLOPRAMIDA, match
#     exacto en OBJECIONES_EMSSANAR) y P32606-02 → raíz 32606 (SODIO LACTATO).
#   - Dispositivos 9101xxxx (catéteres, llaves, electrodos…): catálogo propio
#     de FAMISANAR sin equivalencia conocida → se dejan tal cual y se reportan,
#     hasta tener el maestro (cargarlo vía --mapa-servicios).
_RE_MED_CON_LETRA = re.compile(r"^[A-Za-z](\d[\dA-Za-z.\-]*)$")

# Equivalencias FIJAS dispositivo FAMISANAR → código FMQ del HUS, confirmadas
# por la auditora contra el archivo de trabajo OBJECIONES_LOTE_02 (los insumos
# del HUS van con código FMQ). Evidencia de cada una:
#   91017235 → FMQ0112   CATETER INTRAVENOSO 18 — valor $5.800 idéntico
#   91012136 → FMQ0182-1 LLAVES DE TRES VIAS — nombre exacto (único)
#   91017424 → FMQ0952   ELECTRODO ECG ADULTO — 3×$800 = $2.400 idéntico
#   91017278 → FMQ0159   BOLSA RECOLECTORA DE ORINA ADULTO — $18.100 idéntico
# Un --mapa-servicios de la CLI puede AGREGAR equivalencias o PISAR estas.
MAPA_SERVICIOS_DEFAULT: dict[str, str] = {
    "91017235": "FMQ0112",
    "91012136": "FMQ0182-1",
    "91017424": "FMQ0952",
    "91017278": "FMQ0159",
}


def homologar_cod_servicio(cod: str, mapa: dict[str, str] | None = None) -> tuple[str, str]:
    """Devuelve (codigo_homologado, regla_aplicada). Reglas, en orden:
    'mapa' (equivalencias fijas + las de --mapa-servicios, que pisan a las
    fijas) → 'letra' (quita la letra inicial de medicamentos) → 'igual'
    (CUPS y demás, tal cual)."""
    c = (cod or "").strip()
    if not c:
        return "", "vacio"
    combinado = {**MAPA_SERVICIOS_DEFAULT, **(mapa or {})}
    if c in combinado:
        return combinado[c], "mapa"
    m = _RE_MED_CON_LETRA.match(c)
    if m:
        return m.group(1), "letra"
    return c, "igual"


# ─── Lectura del servicio dentro del texto de la objeción ────────────────────
#
# FAMISANAR no manda el servicio en una columna: el código, el nombre, el valor
# unitario y la cantidad van dentro del texto de la observación. Lo que se saca
# de ahí alimenta el cruce contra el export del DGH (tools/_cruce_dgh.py), que
# es el que traduce todo eso al código que Dinámica Gerencial reconoce.

# Lo que se puede leer del texto de la objeción además del código: el nombre
# del servicio y el valor unitario que FAMISANAR dice haber facturado.
_RE_DESC_TARIFA = re.compile(
    r"PARA\s+EL\s+SERVICIO\s+(?P<desc>.+?)\s+C[ÓO]DIGO", re.IGNORECASE | re.DOTALL
)
_RE_DESC_COBERTURA = re.compile(
    r"SERVICIO\s+SIN\s+COBERTURA\s+(?P<desc>.+?)\s*C[ÓO]DIGO", re.IGNORECASE | re.DOTALL
)
_RE_DESC_AUTORIZACION = re.compile(
    r"(?:\bPOS\b|NO\s+POS)\s+(?P<desc>.+?)\s*C[ÓO]DIGO", re.IGNORECASE | re.DOTALL
)
_RE_DESC_CANTIDAD = re.compile(
    r"CANT\.?\s+DE\s+(?P<desc>.+?)\s+C[ÓO]DIGO", re.IGNORECASE | re.DOTALL
)
_RE_DESC_AUD_EXTRA = re.compile(
    r"SE\s+(?:OBJETAN?|RECONOCE)\s+(?P<desc>.+?)"
    r"(?=\s+(?:CANT|CNT|CAN)\b|\s+C[ÓO]DIGO\b|\s{3,}|[,\.]\s|$)",
    re.IGNORECASE | re.DOTALL,
)
_RE_UNITARIO = re.compile(
    r"VALOR\s+(?:UNITARIO\s+)?FACTURADO\s+POR\s+(?:LA\s+)?IPS\s*(?:DE)?\s*\$?\s*([\d\.,]+)",
    re.IGNORECASE,
)
# Código pegado adelante del nombre ("FMQ0113 CATETER INTRAVENOSO 20") y
# código IUM largo pegado adelante ("1O1044511000101 OXIGENO").
_RE_COD_PEGADO = re.compile(r"^(?P<cod>[A-Z]{2,4}\d[A-Z0-9\-\.]*)\s+(?P<resto>.{4,})$")


def descripcion_del_texto(observacion: str) -> str:
    """El nombre del servicio tal como lo escribió FAMISANAR, sacado del texto."""
    t = " ".join((observacion or "").split())
    if not t:
        return ""
    for rx in (
        _RE_DESC_TARIFA,
        _RE_DESC_COBERTURA,
        _RE_DESC_AUTORIZACION,
        _RE_DESC_CANTIDAD,
        _RE_DESC_AUD_EXTRA,
    ):
        m = rx.search(t)
        if not m:
            continue
        desc = " ".join(m.group("desc").split()).strip(" .-")
        pegado = _RE_COD_PEGADO.match(desc)
        if pegado:
            desc = pegado.group("resto").strip()
        return desc[:300]
    return ""


def valor_unitario_del_texto(observacion: str) -> int:
    """El valor unitario que FAMISANAR declara haber facturado (0 si no viene)."""
    m = _RE_UNITARIO.search(" ".join((observacion or "").split()))
    return _num(m.group(1)) if m else 0


def codigo_servicio_del_texto(observacion: str) -> str:
    """El código del servicio, venga donde venga: detrás de la etiqueta CÓDIGO
    o pegado adelante del nombre ("… SERVICIO SIN COBERTURA  FMQ0113 CATETER
    INTRAVENOSO 20  CÓDIGO   VALOR UNITARIO…", donde la etiqueta va vacía)."""
    cod = extraer_cod_servicio(observacion)
    if cod:
        return cod
    t = " ".join((observacion or "").split())
    for rx in (_RE_DESC_COBERTURA, _RE_DESC_TARIFA, _RE_DESC_AUTORIZACION, _RE_DESC_CANTIDAD):
        m = rx.search(t)
        if not m:
            continue
        cuerpo = " ".join(m.group("desc").split()).strip(" .-")
        pegado = _RE_COD_PEGADO.match(cuerpo)
        if pegado:
            return pegado.group("cod")
        # "DUN0018" solo: el nombre ES el código.
        if re.fullmatch(r"[A-Z]{2,5}\d[A-Z0-9\-\.]*", cuerpo.upper()):
            return cuerpo.upper()
        break
    return ""


_RE_CANTIDAD_TEXTO = re.compile(r"DE\s+(\d+)\s*UNIDAD\(ES\)", re.IGNORECASE)
_RE_CANTIDAD_FACT = re.compile(r"C(?:ANT|NT)\s*F\w*\s*(\d+)", re.IGNORECASE)


def cantidad_del_texto(observacion: str) -> int:
    """Las unidades que FAMISANAR dice haber objetado (0 si no vienen)."""
    t = " ".join((observacion or "").split())
    m = _RE_CANTIDAD_TEXTO.search(t) or _RE_CANTIDAD_FACT.search(t)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


# ─── CROTIPOBJ: tipo de objeción por factura ─────────────────────────────────

GRUPO_CLINICO = "CL"


def crotipobj_factura(grupos: set[str]) -> int:
    """Tipo de objeción de la factura según sus grupos de concepto (2 letras).

    Los tres valores que reconoce DGH: **0 = ADMINISTRATIVA** (sólo TA/FA/SO/
    AU/CO…), **1 = MEDICA** (sólo CL) y **2 = MIXTA** (CL junto con cualquier
    administrativa). Se decide por FACTURA, no por renglón: todas las
    objeciones de una misma factura salen con el mismo valor.
    """
    tiene_cl = GRUPO_CLINICO in grupos
    tiene_admin = any(g != GRUPO_CLINICO for g in grupos)
    if tiene_cl and tiene_admin:
        return 2
    if tiene_cl:
        return 1
    return 0


# ─── Texto de la observación en el formato de trabajo ────────────────────────

_RE_VALOR_FINAL = re.compile(r"\$\s*([\d.,]+)\s*$")


def construir_crdobserv(codigo: str, observacion: str, valor: int) -> str:
    """CRDOBSERV = ``<código> <texto>$<valor>`` (formato de los archivos
    reales). Normaliza las corridas largas de espacios que traen los exports
    de FAMISANAR. Anti-duplicado con cuidado: quita el código del inicio si ya
    viene, y un ``$<monto>`` final SOLO si es el MISMO valor de la objeción.
    Si el monto final es otro (p. ej. "VALOR UNITARIO FACTURADO POR IPS
    $ 244,800" cuando la objeción es 207100), se CONSERVA — es información
    real del texto, no un duplicado (hallazgo de la revisión adversarial:
    18/37 filas del archivo real perdían el valor unitario)."""
    t = " ".join((observacion or "").split())
    cod = (codigo or "").strip()
    if cod and t.upper().startswith(cod.upper()):
        t = t[len(cod) :].strip()
    m = _RE_VALOR_FINAL.search(t)
    if m and _num(m.group(1)) == valor:
        t = t[: m.start()].strip()
    prefijo = f"{cod} " if cod else ""
    return f"{prefijo}{t}${valor}"


# ─── Transformación FAMISANAR → 16 columnas ──────────────────────────────────


def construir_registros(
    ruta: Path,
    fecha: _dt.datetime,
    consecutivo: int,
    codigo_sufijo: str,
    mapa_codigos: dict[str, str] | None,
    mapa_servicios: dict[str, str] | None = None,
    homologar: bool = True,
    servicios_dgh: dict[str, list[LineaDgh]] | None = None,
    trazas: list[dict] | None = None,
) -> list[dict]:
    """Lee el Excel de FAMISANAR y devuelve una lista de dicts, uno por
    objeción, con las 16 columnas del formato de trabajo. Con `homologar`
    (default), el código de servicio extraído del texto se convierte al del
    HUS (ver homologar_cod_servicio); `mapa_servicios` agrega equivalencias
    explícitas (p. ej. los dispositivos 9101xxxx).

    Con `servicios_dgh` (el export de servicios facturados del DGH) se busca
    además, factura por factura, de qué servicio habla cada objeción: cuando
    el cruce es confiable, SLNSERPRO queda con el código REAL del hospital. Si
    no lo es, se deja lo que se sabía por el texto y el renglón queda marcado
    para revisión. CTNCENCOS va siempre vacía (ver el comentario abajo).

    `trazas`, si se pasa, recibe un dict por objeción con el detalle del cruce
    (qué se leyó del texto, con qué renglón del DGH cruzó y por qué). Va aparte
    para que cada registro conserve exactamente las 16 columnas del formato."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl. py -m pip install openpyxl\n")
        sys.exit(2)

    wb = load_workbook(filename=str(ruta), data_only=True, read_only=True)
    ws = wb.active
    filas = ws.iter_rows(values_only=True)
    try:
        headers = list(next(filas))
    except StopIteration:
        logger.warning(f"  {ruta.name}: hoja vacía")
        return []
    idx = _resolver_columnas([str(h) for h in headers])

    consec_por_factura: dict[str, int] = {}
    sin_codigo = 0
    cruces: dict[str, int] = defaultdict(int)
    homologados: dict[str, int] = defaultdict(int)
    sin_regla: dict[str, str] = {}

    registros: list[dict] = []
    for r in filas:
        if r is None:
            continue
        factura_raw = str(_cell(r, idx, "factura") or "").strip()
        observacion = str(_cell(r, idx, "observacion") or "").strip()
        cod_dev = str(_cell(r, idx, "codigo_devolucion") or "").strip()
        if not factura_raw and not observacion and not cod_dev:
            continue

        crncxc = factura_larga(factura_raw)
        if crncxc not in consec_por_factura:
            consec_por_factura[crncxc] = consecutivo + len(consec_por_factura)
        codigo = codigo_objecion(cod_dev, codigo_sufijo, mapa_codigos)
        valor = _num(_cell(r, idx, "valor"))
        cod_servicio = codigo_servicio_del_texto(observacion)
        cod_famisanar, regla = "", ""
        if not cod_servicio:
            sin_codigo += 1
        elif homologar:
            cod_famisanar = cod_servicio
            cod_servicio, regla = homologar_cod_servicio(cod_famisanar, mapa_servicios)
            homologados[regla] += 1

        # Cruce contra los servicios que el DGH tiene facturados en ESA factura.
        cruce = Cruce()
        if servicios_dgh is not None:
            cruce = resolver_servicio(
                servicios_dgh.get(crncxc, []),
                codigo=cod_famisanar or cod_servicio,
                descripcion=descripcion_del_texto(observacion),
                valor=valor,
                valor_unitario=valor_unitario_del_texto(observacion),
                cantidad=cantidad_del_texto(observacion),
            )
            cruces[cruce.confianza] += 1
            if cruce.linea is not None:
                # Manda el código del hospital: es el que DGH reconoce.
                cod_servicio = cruce.linea.codigo or cod_servicio
        # Dispositivos FAMISANAR (9101xxxx…) sin equivalencia HUS: se reportan
        # para completar el mapa con el maestro, pero sólo los que el cruce
        # contra el DGH tampoco pudo ubicar — con el export a la mano la
        # mayoría se resuelve sola y no hay nada que cargar al mapa.
        if (
            cod_famisanar
            and regla == "igual"
            and not re.fullmatch(r"\d{6}", cod_famisanar)
            and cruce.linea is None
        ):
            sin_regla[cod_famisanar] = observacion[:60]

        registros.append(
            {
                "CDCONSEC": str(consec_por_factura[crncxc]),
                "CDFECDOC": fecha,
                "CRNCXC": crncxc,
                "CROFECOBJ": fecha,
                "CROREFERE": None,
                "CROOBSERV": None,
                "CROCLAOBJ": CROCLAOBJ_CONST,
                "CRNCLAOBJ": None,
                "GENUSUARIO4": GENUSUARIO4_CONST,
                "CRNCONOBJ": codigo,
                "SLNSERPRO": cod_servicio or None,
                "IDRIPS": None,
                # CTNCENCOS va SIEMPRE vacía en el archivo de FAMISANAR (regla
                # del área). El export del DGH sólo trae el NOMBRE del centro
                # de costo ("URGENCIAS ADULTOS") y esta columna es de código,
                # así que llenarla con el nombre sería escribir un dato que no
                # corresponde. El nombre sí queda en el reporte de cruce, para
                # que el auditor pueda ubicar el renglón.
                "CTNCENCOS": None,
                "CROVALOBJ": valor,
                "CRDOBSERV": construir_crdobserv(codigo, observacion, valor),
                "CROTIPOBJ": 0,  # placeholder: se calcula por factura abajo
            }
        )
        if trazas is not None:
            trazas.append(
                traza(
                    factura=crncxc,
                    codigo_objecion=codigo,
                    valor=valor,
                    cod_entidad=codigo_servicio_del_texto(observacion),
                    desc_entidad=descripcion_del_texto(observacion),
                    unitario_entidad=valor_unitario_del_texto(observacion),
                    observacion=observacion,
                    cruce=cruce,
                )
            )
    wb.close()

    # CROTIPOBJ por factura según la mezcla de conceptos.
    grupos_por_factura: dict[str, set[str]] = defaultdict(set)
    for reg in registros:
        grupos_por_factura[reg["CRNCXC"]].add(str(reg["CRNCONOBJ"])[:2].upper())
    for reg in registros:
        reg["CROTIPOBJ"] = crotipobj_factura(grupos_por_factura[reg["CRNCXC"]])

    if sin_codigo:
        logger.info(
            f"  ⚠ {sin_codigo} objeciones sin código de servicio en el texto "
            "(filas 'AUD EXTRA'): SLNSERPRO queda vacío."
        )
    if homologar and homologados:
        partes = []
        if homologados.get("igual"):
            partes.append(f"{homologados['igual']} tal cual (CUPS/otros)")
        if homologados.get("letra"):
            partes.append(f"{homologados['letra']} con letra FAMISANAR quitada (U/P…)")
        if homologados.get("mapa"):
            partes.append(f"{homologados['mapa']} por mapa de equivalencias")
        logger.info(f"  Homologación de códigos de servicio: {', '.join(partes)}.")
    if servicios_dgh is not None:
        total = sum(cruces.values()) or 1
        ubicados = cruces["ALTA"] + cruces["MEDIA"]
        logger.info(
            f"  Cruce contra los servicios del DGH: {ubicados} de {total} servicios "
            f"ubicados con confianza alta/media ({ubicados / total:.0%})."
        )
        logger.info(
            f"    ALTA={cruces['ALTA']}  MEDIA={cruces['MEDIA']}  BAJA={cruces['BAJA']}  "
            f"SIN CRUCE={cruces['SIN CRUCE']}  → revisar {cruces['BAJA'] + cruces['SIN CRUCE']}."
        )
    if sin_regla:
        logger.warning(
            f"  ⚠ {len(sin_regla)} códigos de FAMISANAR SIN equivalencia HUS conocida "
            "(dispositivos): quedan tal cual. Completalos con --mapa-servicios:"
        )
        for cod, desc in sorted(sin_regla.items()):
            logger.warning(f"      {cod}  ← {desc}…")
    return registros


# ─── Escritura ───────────────────────────────────────────────────────────────


def _escribir_hoja(registros: list[dict], salida: Path) -> None:
    """Escribe UN .xlsx con hoja OBJECIONES y las 16 columnas del formato."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "OBJECIONES"

    fill_hdr = PatternFill("solid", fgColor="1F4E78")
    font_hdr = Font(bold=True, color="FFFFFF")
    for col, nombre in enumerate(COLUMNAS_DISPENSARIO, start=1):
        c = ws.cell(row=1, column=col, value=nombre)
        c.fill = fill_hdr
        c.font = font_hdr

    fila = 2
    for reg in registros:
        for col, nombre in enumerate(COLUMNAS_DISPENSARIO, start=1):
            celda = ws.cell(row=fila, column=col, value=reg.get(nombre))
            celda.number_format = FORMATOS_DISPENSARIO[nombre]
        fila += 1

    ws.freeze_panes = "A2"
    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(salida))


PREFIJO_DEFAULT = "OBJECIONES_FAMISANAR"


def escribir_por_factura(
    registros: list[dict],
    carpeta: Path,
    prefijo: str = PREFIJO_DEFAULT,
    consecutivo: int = CDCONSEC_DEFAULT,
) -> list[Path]:
    """Un archivo <prefijo>_<CRNCXC>.xlsx por factura. Cada archivo standalone
    lleva UNA factura, así que su CDCONSEC se reinicia a `consecutivo` (texto)."""
    por_factura: dict[str, list[dict]] = defaultdict(list)
    for reg in registros:
        por_factura[reg["CRNCXC"]].append(reg)

    generados: list[Path] = []
    for crncxc, regs in sorted(por_factura.items()):
        # Copia por registro: NO se muta la lista original — un consolidado
        # posterior sobre los mismos registros perdería el 1,2,3… por factura
        # (hallazgo de la revisión adversarial).
        regs_out = [{**reg, "CDCONSEC": str(consecutivo)} for reg in regs]
        destino = carpeta / f"{prefijo}_{crncxc}.xlsx"
        _escribir_hoja(regs_out, destino)
        generados.append(destino)
        logger.info(f"  {destino.name}: {len(regs)} objeciones")
    return generados


def escribir_consolidado(registros: list[dict], salida: Path) -> None:
    """Un único archivo con todas las facturas (CDCONSEC 1,2,3… por factura)."""
    _escribir_hoja(registros, salida)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _cargar_mapa(ruta: Path | None) -> dict[str, str]:
    if ruta is None:
        return {}
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"No pude leer el mapa de códigos {ruta}: {e}")
        sys.exit(2)
    if not isinstance(data, dict):
        logger.error('El mapa de códigos debe ser un objeto JSON {"CL08": "CL0801", ...}')
        sys.exit(2)
    return {str(k).strip().upper(): str(v).strip() for k, v in data.items()}


def _parse_fecha(texto: str | None) -> _dt.datetime:
    if not texto:
        hoy = _dt.date.today()
        return _dt.datetime(hoy.year, hoy.month, hoy.day)
    try:
        return _dt.datetime.strptime(texto.strip(), "%Y-%m-%d")
    except ValueError:
        logger.error(f"--fecha inválida: {texto!r} (usá YYYY-MM-DD, p.ej. 2026-08-13)")
        sys.exit(2)


def _resumen(registros: list[dict]) -> None:
    facturas = defaultdict(int)
    codigos = defaultdict(int)
    total = 0
    for reg in registros:
        facturas[reg["CRNCXC"]] += 1
        codigos[reg["CRNCONOBJ"]] += 1
        total += reg["CROVALOBJ"]
    logger.info(f"  Facturas: {len(facturas)}  |  Objeciones: {len(registros)}")
    logger.info(f"  Valor glosado total: ${total:,.0f}")
    logger.info("  Códigos de objeción (CRNCONOBJ):")
    for cod, n in sorted(codigos.items(), key=lambda kv: (-kv[1], kv[0])):
        logger.info(f"    {cod or '(sin código)'}: {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        required=True,
        help="Excel de FAMISANAR (4 columnas: NRO_FACTURA, CODIGO_DEVOLUCION, "
        "VALOR DEVOLUCION, OBSERVACION).",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        required=True,
        help="Carpeta destino (un archivo <prefijo>_<factura>.xlsx por factura), "
        "o archivo .xlsx si se usa --consolidado.",
    )
    parser.add_argument(
        "--prefijo",
        default=PREFIJO_DEFAULT,
        help=f"Prefijo del nombre de cada archivo por factura. Default: {PREFIJO_DEFAULT}.",
    )
    parser.add_argument(
        "--consolidado",
        action="store_true",
        help="En vez de un archivo por factura, junta todo en un solo Excel (--salida es el .xlsx).",
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="Fecha para CDFECDOC/CROFECOBJ (YYYY-MM-DD). Default: hoy.",
    )
    parser.add_argument(
        "--codigo-sufijo",
        default=CODIGO_SUFIJO_DEFAULT,
        help="Consecutivo con que se completaría un código de 4 chars (red de seguridad). "
        f"Default: {CODIGO_SUFIJO_DEFAULT}.",
    )
    parser.add_argument(
        "--mapa-codigos",
        type=Path,
        default=None,
        help='JSON opcional para forzar códigos de objeción: {"CO0701": "CO0702", ...}.',
    )
    parser.add_argument(
        "--mapa-servicios",
        type=Path,
        default=None,
        help="JSON con equivalencias FAMISANAR→HUS para códigos de SERVICIO sin regla "
        '(los dispositivos 9101xxxx): {"91017235": "<código HUS>", ...}.',
    )
    parser.add_argument(
        "--servicios-dgh",
        type=Path,
        default=None,
        help="Export de servicios facturados del DGH (columnas SERVICIOS DGH, "
        "DESCRIPCION INSTITUCIONAL, NOM_CENTRO_COSTO, FACTURA, CAT_SERVICIOS, "
        "Vr_SERVICIO). Con él, SLNSERPRO queda con el código real del hospital.",
    )
    parser.add_argument(
        "--reporte-cruce",
        type=Path,
        default=None,
        help="Excel de trabajo con el detalle del cruce (hojas CRUCE, REVISAR y "
        "RESUMEN). Requiere --servicios-dgh.",
    )
    parser.add_argument(
        "--sin-homologar",
        action="store_true",
        help="Deja en SLNSERPRO el código tal cual viene de FAMISANAR (sin quitar la "
        "letra de medicamentos ni aplicar el mapa de servicios).",
    )
    parser.add_argument(
        "--consecutivo",
        type=int,
        default=CDCONSEC_DEFAULT,
        help=f"Número inicial del consecutivo por factura (CDCONSEC). Default: {CDCONSEC_DEFAULT}.",
    )
    parser.add_argument("--log", type=Path, default=None, help="Guarda un log adicional a archivo.")
    args = parser.parse_args(argv)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=handlers
    )

    if not args.entrada.is_file():
        logger.error(f"No existe el archivo de entrada: {args.entrada}")
        return 1

    if args.reporte_cruce is not None and args.servicios_dgh is None:
        logger.error("--reporte-cruce necesita --servicios-dgh (es el detalle de ese cruce).")
        return 1

    fecha = _parse_fecha(args.fecha)
    mapa = _cargar_mapa(args.mapa_codigos)
    mapa_servicios = _cargar_mapa(args.mapa_servicios)

    servicios_dgh = None
    if args.servicios_dgh is not None:
        if not args.servicios_dgh.is_file():
            logger.error(f"No existe el export del DGH: {args.servicios_dgh}")
            return 1
        logger.info(f"Leyendo servicios facturados del DGH: {args.servicios_dgh.name}")
        try:
            servicios_dgh = leer_servicios_dgh(args.servicios_dgh, avisar=logger.warning)
        except ValueError as e:
            logger.error(str(e))
            return 1
        logger.info(
            f"  {sum(len(v) for v in servicios_dgh.values())} renglones de servicio "
            f"en {len(servicios_dgh)} facturas."
        )

    trazas: list[dict] = []
    logger.info(f"Leyendo glosas de FAMISANAR: {args.entrada.name}")
    registros = construir_registros(
        args.entrada,
        fecha=fecha,
        consecutivo=args.consecutivo,
        codigo_sufijo=args.codigo_sufijo,
        mapa_codigos=mapa,
        mapa_servicios=mapa_servicios,
        homologar=not args.sin_homologar,
        servicios_dgh=servicios_dgh,
        trazas=trazas,
    )
    if not registros:
        logger.error("No se encontró ninguna objeción en el archivo de entrada.")
        return 1

    if args.consolidado:
        escribir_consolidado(registros, args.salida)
        logger.info(f"\nExcel de FAMISANAR (consolidado, formato de trabajo): {args.salida}")
    else:
        generados = escribir_por_factura(
            registros, args.salida, prefijo=args.prefijo, consecutivo=args.consecutivo
        )
        logger.info(f"\n{len(generados)} archivo(s) de FAMISANAR en: {args.salida}")

    if args.reporte_cruce is not None:
        escribir_reporte_cruce(trazas, args.reporte_cruce, entidad="FAMISANAR")
        pendientes = sum(1 for t in trazas if t["aviso"] or t["confianza"] in ("BAJA", "SIN CRUCE"))
        logger.info(
            f"Detalle del cruce: {args.reporte_cruce} "
            f"({pendientes} renglón(es) en la hoja REVISAR)."
        )

    _resumen(registros)
    return 0


if __name__ == "__main__":
    sys.exit(main())
