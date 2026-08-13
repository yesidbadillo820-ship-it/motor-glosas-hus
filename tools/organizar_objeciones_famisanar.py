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
    SLNSERPRO    ← extraído del texto ("CÓDIGO <x>") y HOMOLOGADO al código HUS:
                   CUPS tal cual; medicamentos U/P → se quita la letra
                   (U20162259-04 → 20162259-04); dispositivos 9101xxxx → tal
                   cual + aviso (completar con --mapa-servicios)
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
    """Convierte a entero tolerando '$1.234', '1,234', floats, None."""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[^\d\-]", "", str(v))
    if not s or s == "-":
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


# ─── Normalización de factura (corta → larga) ────────────────────────────────

_RE_FACTURA = re.compile(r"^([A-Za-z]+)0*(\d+)$")


def factura_larga(fac: object, ancho: int = 10) -> str:
    """HUS532670 → HUS0000532670 (rellena con ceros a `ancho` dígitos).
    Idempotente. Si no matchea el patrón, devuelve el texto tal cual."""
    s = str(fac or "").strip()
    m = _RE_FACTURA.match(s)
    if not m:
        return s
    return m.group(1).upper() + m.group(2).zfill(ancho)


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
    Devuelve '' si el texto no trae código (p. ej. filas 'AUD EXTRA - …')."""
    m = _RE_COD_SERVICIO.search(observacion or "")
    return m.group(1).strip(".-") if m else ""


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


def homologar_cod_servicio(cod: str, mapa: dict[str, str] | None = None) -> tuple[str, str]:
    """Devuelve (codigo_homologado, regla_aplicada). Reglas, en orden:
    'mapa' (equivalencia explícita de --mapa-servicios) → 'letra' (quita la
    letra inicial de medicamentos) → 'igual' (CUPS y demás, tal cual)."""
    c = (cod or "").strip()
    if not c:
        return "", "vacio"
    if mapa and c in mapa:
        return mapa[c], "mapa"
    m = _RE_MED_CON_LETRA.match(c)
    if m:
        return m.group(1), "letra"
    return c, "igual"


# ─── CROTIPOBJ: tipo de objeción por factura ─────────────────────────────────

GRUPO_CLINICO = "CL"


def crotipobj_factura(grupos: set[str]) -> int:
    """Tipo de objeción de la factura según sus grupos de concepto (2 letras):
    solo administrativos (TA/FA/SO/AU/CO…) → 0; solo CL → 1; mezcla con CL → 2.
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
) -> list[dict]:
    """Lee el Excel de FAMISANAR y devuelve una lista de dicts, uno por
    objeción, con las 16 columnas del formato de trabajo. Con `homologar`
    (default), el código de servicio extraído del texto se convierte al del
    HUS (ver homologar_cod_servicio); `mapa_servicios` agrega equivalencias
    explícitas (p. ej. los dispositivos 9101xxxx)."""
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
        cod_servicio = extraer_cod_servicio(observacion)
        if not cod_servicio:
            sin_codigo += 1
        elif homologar:
            cod_famisanar = cod_servicio
            cod_servicio, regla = homologar_cod_servicio(cod_famisanar, mapa_servicios)
            homologados[regla] += 1
            # Dispositivos FAMISANAR (9101xxxx…) sin equivalencia: quedan tal
            # cual pero se reportan para completar el mapa con el maestro HUS.
            if regla == "igual" and not re.fullmatch(r"\d{6}", cod_famisanar):
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
                "CTNCENCOS": None,
                "CROVALOBJ": valor,
                "CRDOBSERV": construir_crdobserv(codigo, observacion, valor),
                "CROTIPOBJ": 0,  # placeholder: se calcula por factura abajo
            }
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

    fecha = _parse_fecha(args.fecha)
    mapa = _cargar_mapa(args.mapa_codigos)
    mapa_servicios = _cargar_mapa(args.mapa_servicios)

    logger.info(f"Leyendo glosas de FAMISANAR: {args.entrada.name}")
    registros = construir_registros(
        args.entrada,
        fecha=fecha,
        consecutivo=args.consecutivo,
        codigo_sufijo=args.codigo_sufijo,
        mapa_codigos=mapa,
        mapa_servicios=mapa_servicios,
        homologar=not args.sin_homologar,
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

    _resumen(registros)
    return 0


if __name__ == "__main__":
    sys.exit(main())
