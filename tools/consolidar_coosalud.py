"""consolidar_coosalud.py — Consolida GLOSAS/DETALLES/FACTURAS de COOSALUD y arma el archivo de OBJECIONES (DGH).

Automatiza los pasos manuales que siguen después de organizar el ZIP con
`organizar_cargue_masivo_coosalud.py` (puntos 2 a 5 de la guía de cartera):

  1. CONSOLIDADO GLOSAS.xlsx
       - Hoja GLOSAS: todas las filas de GLOSAS HUS*.xlsx + columna
         OBSERVACION FINAL = codigo_glosa + " " + justificacion_glosa + "$" + valor_total_glosa
       - Hoja AGRUPADO: una fila por id_detalle con las observaciones combinadas
         (reemplaza el "Agrupar por" + Text.Combine de Power Query).
  2. CONSOLIDADO DETALLE.xlsx
       - Todas las filas de DETALLE HUS*.xlsx + columna OBSERVACION FINAL
         buscada por id_detalle (reemplaza el BUSCARV).
  3. CONSOLIDADO FACTURAS.xlsx
       - Todas las filas de HUS*.xlsx (cabeceras de factura).
  4. SERVICIOS FACTURADOS COOSALUD.xlsx  (solo si se pasa --servicios)
       - La base DGH filtrada: SOLO las facturas trabajadas y SOLO 10 columnas.
       - "Arreglada": en los medicamentos (que vienen con SLNSERPRO_SERVICIO
         vacío) se rellenan SERVICIO/CUPS y descripciones con el código y
         nombre del medicamento, igual que en el proceso manual.
       - Se lee en streaming: la base puede pesar 80MB+ sin agotar la memoria.
  5. OBJECIONES.xlsx  (formato de cargue DGH, igual al archivo de ejemplo)
       - Una fila por servicio glosado (id_detalle con glosas):
         CDCONSEC    consecutivo por factura, como texto (1,1,1... 2,2,2...)
         CDFECDOC    --fecha como fecha Excel (día de la carpeta que se revisa)
         CRNCXC      factura con ceros: HUS0000496207
         CROFECOBJ   --fecha
         CROREFERE / CROOBSERV / CRNCLAOBJ / IDRIPS / CTNCENCOS   vacíos
         CROCLAOBJ   0
         GENUSUARIO4 999 (texto)
         CRNCONOBJ   código completo de la glosa de MAYOR valor del servicio (TA2901, CL0201...)
         SLNSERPRO   codigo_servicio del DETALLE; si se pasa la base DGH y la
                     fila cruza, manda el código DGH (con sufijo H si lo trae);
                     si hay base y no cruza, va a la hoja NO_CRUZADOS
         CROVALOBJ   valor_glosado del servicio (número)
         CRDOBSERV   OBSERVACION FINAL combinada (una línea por glosa)
         CROTIPOBJ   por FACTURA completa: 0=administrativa (sin CL) ·
                     1=médica (solo CL) · 2=mixta (CL + otros) — si la factura
                     es mixta, TODAS sus filas llevan 2

DEFENSAS (validado con revisión adversarial):
  - Valores en formato colombiano ("1.234.567,89", "26,140") se parsean bien.
  - Archivos ~$ de Excel se ignoran; un xlsx corrupto aborta con nombre claro.
  - Si un lote trae los encabezados en otro orden, las filas se reordenan por nombre.
  - id_detalle/códigos tipados como número (123456.0) cruzan igual.
  - Archivos o filas duplicadas (mismo id_glosa / id_detalle) se saltan con aviso
    para no duplicar el valor objetado.
  - xlsx del portal con "dimension" mentirosa se leen completos (reset_dimensions).
  - Facturas que no siguen el patrón HUS se reportan.

USO
---

    REM Después de organizar el ZIP (los consolidados salen en <carpeta>\\CONSOLIDADOS)
    py consolidar_coosalud.py ^
        --carpeta "D:\\USUARIO CARTERA\\Desktop\\CARGUE MASIVO COOSALUD" ^
        --fecha 04/07/2026

    REM Con la base DGH para el punto 4 y el cruce SLNSERPRO del punto 5
    py consolidar_coosalud.py ^
        --carpeta   "D:\\USUARIO CARTERA\\Desktop\\CARGUE MASIVO COOSALUD" ^
        --fecha     04/07/2026 ^
        --servicios "D:\\...\\SERVICIOS FACTURADOS COOSALUD DGH.xlsx"

INSTALACIÓN (una vez):
    py -m pip install openpyxl
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterator

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    print("Falta openpyxl. Instalar con:  py -m pip install openpyxl")
    sys.exit(1)

logger = logging.getLogger("consolidar_coosalud")

# --- Estructura de la carpeta organizada (ver organizar_cargue_masivo_coosalud) ---
CARPETA_GLOSAS = "GLOSAS"
CARPETA_DETALLES = "DETALLES"
CARPETA_FACTURAS = "FACTURAS"
SALIDA_DEFECTO = "CONSOLIDADOS"

# Columnas mínimas que se esperan en los archivos del portal.
COL_GLOSAS_REQ = [
    "id_detalle",
    "numero_factura",
    "codigo_glosa",
    "justificacion_glosa",
    "valor_total_glosa",
]
COL_DETALLE_REQ = ["id_detalle", "numero_factura", "codigo_servicio", "valor_glosado"]

# Columnas que se conservan de la base DGH, ya "arreglada" (punto 4 de la guía).
COLS_SERVICIOS = [
    "FACTURA",
    "SLNSERPRO_SERVICIO",
    "DESCRIPCION INSTITUCIONAL",
    "SLNSERPRO_CUPS",
    "DESCRIPCION CUPS",
    "CODIGO_MEDICAMENTO",
    "NOMBRE_MEDICAMENTO",
    "CAT_SERVICIOS",
    "Vr_SERVICIO",
    "SALDO_FACT",
]
# Columnas de COLS_SERVICIOS que llevan códigos (se normalizan, ej. 890466.0 -> 890466).
COLS_SERVICIOS_CODIGO = {"SLNSERPRO_SERVICIO", "SLNSERPRO_CUPS", "CODIGO_MEDICAMENTO"}

# Encabezados y formatos de celda del archivo de OBJECIONES (tomados de la
# plantilla DGH real: fechas mm-dd-yy, valores con miles, el resto texto).
COLS_OBJECIONES = [
    ("CDCONSEC", "@"),
    ("CDFECDOC", "mm-dd-yy"),
    ("CRNCXC", "@"),
    ("CROFECOBJ", "mm-dd-yy"),
    ("CROREFERE", "@"),
    ("CROOBSERV", "@"),
    ("CROCLAOBJ", "General"),
    ("CRNCLAOBJ", "@"),
    ("GENUSUARIO4", "@"),
    ("CRNCONOBJ", "@"),
    ("SLNSERPRO", "@"),
    ("IDRIPS", "@"),
    ("CTNCENCOS", "@"),
    ("CROVALOBJ", '_-* #,##0_-;\\-* #,##0_-;_-* "-"_-;_-@_-'),
    ("CRDOBSERV", "@"),
    ("CROTIPOBJ", "0"),
]

RE_NUM_FACTURA = re.compile(r"HUS0*(\d+)", re.IGNORECASE)


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


# --------------------------------------------------------------------------- utilidades
def norm_texto(s: object) -> str:
    return str(s).strip() if s is not None else ""


def norm_header(s: object) -> str:
    """Normaliza un encabezado para compararlo (mayúsculas, sin espacios dobles)."""
    return re.sub(r"\s+", " ", norm_texto(s)).upper()


def _num_factura(s: object) -> int | None:
    """Extrae el número de la factura: HUS0000512396 / HUS512396 / 512396 -> 512396."""
    txt = norm_texto(s).upper()
    m = RE_NUM_FACTURA.search(txt)
    if m:
        return int(m.group(1))
    if txt.isdigit():
        return int(txt)
    return None


def norm_factura(s: object) -> str:
    """Clave de cruce: HUS0000512396 / HUS512396 / 512396 -> HUS512396."""
    n = _num_factura(s)
    return f"HUS{n}" if n is not None else norm_texto(s).upper()


def factura_dgh(s: object) -> str:
    """Factura en el formato del archivo de objeciones: HUS + 10 dígitos (HUS0000496207)."""
    n = _num_factura(s)
    return f"HUS{n:010d}" if n is not None else norm_texto(s).upper()


def norm_codigo(s: object) -> str:
    """Código/ID para cruce: texto plano en mayúsculas, sin el '.0' que Excel
    agrega cuando la celda viene tipada como número (890466.0 -> 890466)."""
    txt = norm_texto(s).upper()
    if re.fullmatch(r"\d+\.0", txt):
        txt = txt[:-2]
    return txt


def a_numero(v: object) -> float | None:
    """Convierte un valor monetario a número. Maneja formato colombiano
    ("1.234.567,89"), US ("1,234,567.89"), miles sueltos ("26,140" / "1.234.567")
    y negativos contables. Devuelve None si no es un número.
    (Misma convención que app/services/recepcion_service._a_float.)
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = norm_texto(v)
    if not s:
        return None
    negativo = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not any(c.isdigit() for c in s):
        return None

    tiene_punto, tiene_coma = "." in s, "," in s
    if tiene_punto and tiene_coma:
        # El separador decimal es el que aparece más a la derecha.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.234.567,89
        else:
            s = s.replace(",", "")  # 1,234,567.89
    elif tiene_coma:
        # Una sola coma con 1-2 decimales -> decimal; si no, miles.
        if s.count(",") == 1 and len(s.split(",")[1]) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif tiene_punto:
        # Un solo punto con 1-2 decimales -> decimal; si no, miles.
        if not (s.count(".") == 1 and len(s.split(".")[1]) in (1, 2)):
            s = s.replace(".", "")

    try:
        n = float(s)
    except ValueError:
        return None
    return -n if negativo else n


def fmt_valor(v: object) -> str:
    """Valor para concatenar en OBSERVACION FINAL: entero sin decimales
    (26140) o con hasta 2 decimales (26140.5), nunca notación científica."""
    n = a_numero(v)
    if n is None:
        return norm_texto(v)
    if n == int(n):
        return str(int(n))
    return f"{n:.2f}".rstrip("0").rstrip(".")


def valor_o_numero(v: object) -> object:
    """Para celdas de valores: número real si se puede, si no el texto original."""
    n = a_numero(v)
    if n is None:
        return norm_texto(v)
    return int(n) if n == int(n) else n


def leer_xlsx(path: Path) -> tuple[list[str], list[list]]:
    """Lee la primera hoja: (encabezados, filas). Filas vacías se descartan.

    - reset_dimensions(): algunos xlsx de portales declaran un rango menor al
      real y openpyxl en read_only los leería vacíos/truncados.
    - Un archivo corrupto o bloqueado aborta con el nombre del archivo.
    """
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(
            f"No se pudo leer '{path.name}': {exc}. "
            "¿Archivo corrupto, incompleto o abierto en Excel?"
        ) from exc
    try:
        ws = wb.active
        ws.reset_dimensions()
        it = ws.iter_rows(values_only=True)
        headers = [norm_texto(h) for h in next(it, [])]
        filas = []
        for row in it:
            if row is None or all(c is None or norm_texto(c) == "" for c in row):
                continue
            filas.append(list(row))
        return headers, filas
    finally:
        wb.close()


def buscar_archivos(carpeta: Path, subcarpeta: str, patron: str) -> list[Path]:
    """Busca recursivo (cubre LOTE 01, LOTE 02... o estructura plana).

    Ignora los archivos de bloqueo de Excel (~$...) y ocultos.
    """
    base = carpeta / subcarpeta
    if not base.is_dir():
        return []
    return sorted(
        (p for p in base.rglob(patron) if not p.name.startswith(("~$", "."))),
        key=lambda p: p.name.upper(),
    )


def indice_columnas(headers: list[str], requeridas: list[str], contexto: str) -> dict[str, int]:
    """Mapa nombre_columna -> posición. Falla claro si falta una requerida."""
    mapa = {norm_header(h): i for i, h in enumerate(headers)}
    idx = {}
    for col in requeridas:
        pos = mapa.get(norm_header(col))
        if pos is None:
            raise ValueError(
                f"{contexto}: no se encontró la columna '{col}'. Encabezados: {headers}"
            )
        idx[col] = pos
    return idx


def alinear_filas(
    headers: list[str], filas: list[list], headers_base: list[str], contexto: str
) -> list[list]:
    """Deja las filas en el orden de columnas de headers_base.

    Si los encabezados coinciden solo rellena filas cortas; si vienen en otro
    orden (o con columnas extra/faltantes) las reordena POR NOMBRE y avisa,
    para que el consolidado nunca quede desalineado en silencio.
    """
    norm_b = [norm_header(h) for h in headers_base]
    norm_f = [norm_header(h) for h in headers]
    if norm_f == norm_b:
        n = len(headers_base)
        return [f + [None] * (n - len(f)) if len(f) < n else f for f in filas]

    logger.warning(
        "  %s: encabezados distintos al primer archivo; se reordenan por nombre.", contexto
    )
    extras = [h for h in norm_f if h not in set(norm_b)]
    if extras:
        logger.warning("    columnas extra ignoradas: %s", ", ".join(extras[:6]))
    pos = {h: i for i, h in enumerate(norm_f)}
    return [[f[pos[h]] if h in pos and pos[h] < len(f) else None for h in norm_b] for f in filas]


def escribir_hoja(
    ws, headers: list[str], filas: list[list], formatos: list[str] | None = None
) -> None:
    ws.append(headers)
    for f in filas:
        ws.append(f)
    if formatos:
        for col_i, fmt in enumerate(formatos, start=1):
            if fmt in ("General", None):
                continue
            for row_i in range(2, len(filas) + 2):
                ws.cell(row=row_i, column=col_i).number_format = fmt
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(str(h)) + 4))


# --------------------------------------------------------------------------- pasos
def consolidar_glosas(archivos: list[Path]) -> tuple[list[str], list[list], dict[str, dict]]:
    """Une los GLOSAS *.xlsx, agrega OBSERVACION FINAL y agrupa por id_detalle.

    Deduplica por id_glosa (archivos o filas repetidas se saltan con aviso).

    Devuelve (headers, filas, agrupado) donde agrupado[id_detalle_norm] = {
        'observacion':  texto combinado con saltos de línea,
        'conceptos':    set de prefijos de 2 letras (TA, CL, ...),
        'codigo_mayor': codigo_glosa completo de la glosa de mayor valor,
        'max_valor':    valor de esa glosa,
    }.
    """
    headers_base: list[str] | None = None
    filas: list[list] = []
    agrupado: dict[str, dict] = {}
    vistas: set = set()
    duplicadas = 0

    for arch in archivos:
        headers, rows = leer_xlsx(arch)
        if not rows:
            logger.warning("  (vacío) %s", arch.name)
            continue
        if headers_base is None:
            headers_base = headers
        rows = alinear_filas(headers, rows, headers_base, arch.name)
        idx = indice_columnas(headers_base, COL_GLOSAS_REQ, arch.name)
        mapa_h = {norm_header(h): i for i, h in enumerate(headers_base)}
        idx_id_glosa = mapa_h.get("ID_GLOSA")

        for row in rows:
            # Clave de duplicado: id_glosa si existe; si no, la fila completa.
            if idx_id_glosa is not None and norm_texto(row[idx_id_glosa]):
                clave = norm_codigo(row[idx_id_glosa])
            else:
                clave = tuple(norm_texto(c) for c in row)
            if clave in vistas:
                duplicadas += 1
                continue
            vistas.add(clave)

            codigo = norm_texto(row[idx["codigo_glosa"]])
            justif = norm_texto(row[idx["justificacion_glosa"]])
            valor = row[idx["valor_total_glosa"]]
            obs = f"{codigo} {justif}${fmt_valor(valor)}"
            filas.append(list(row) + [obs])

            id_det = norm_codigo(row[idx["id_detalle"]])
            g = agrupado.setdefault(
                id_det,
                {"observacion": [], "conceptos": set(), "codigo_mayor": "", "max_valor": None},
            )
            g["observacion"].append(obs)
            g["conceptos"].add(codigo[:2].upper())
            v = a_numero(valor)
            if not g["codigo_mayor"]:
                g["codigo_mayor"] = codigo
                g["max_valor"] = v
            elif v is not None and (g["max_valor"] is None or v > g["max_valor"]):
                g["codigo_mayor"] = codigo
                g["max_valor"] = v

    if duplicadas:
        logger.warning("  OJO: %d glosas duplicadas se saltaron (archivos repetidos).", duplicadas)

    for g in agrupado.values():
        g["observacion"] = "\n".join(g["observacion"])

    if headers_base is None:
        raise ValueError("No se encontró ningún archivo GLOSAS con datos.")
    return headers_base + ["OBSERVACION FINAL"], filas, agrupado


def consolidar_detalles(
    archivos: list[Path], agrupado: dict[str, dict]
) -> tuple[list[str], list[list], list[dict]]:
    """Une los DETALLE *.xlsx + OBSERVACION FINAL por id_detalle.

    Deduplica por id_detalle (un servicio repetido duplicaría el valor objetado).
    Devuelve además la lista de servicios glosados (insumo de OBJECIONES).
    """
    headers_base: list[str] | None = None
    filas: list[list] = []
    glosados: list[dict] = []
    vistos: set = set()
    duplicados = 0

    for arch in archivos:
        headers, rows = leer_xlsx(arch)
        if not rows:
            logger.warning("  (vacío) %s", arch.name)
            continue
        if headers_base is None:
            headers_base = headers
        rows = alinear_filas(headers, rows, headers_base, arch.name)
        idx = indice_columnas(headers_base, COL_DETALLE_REQ, arch.name)

        for row in rows:
            id_det = norm_codigo(row[idx["id_detalle"]])
            if id_det in vistos:
                duplicados += 1
                continue
            vistos.add(id_det)

            g = agrupado.get(id_det)
            obs = g["observacion"] if g else ""
            filas.append(list(row) + [obs])

            if g:
                glosados.append(
                    {
                        "factura": norm_texto(row[idx["numero_factura"]]),
                        "id_detalle": id_det,
                        "codigo_servicio": norm_texto(row[idx["codigo_servicio"]]),
                        "valor_glosado": valor_o_numero(row[idx["valor_glosado"]]),
                        "observacion": obs,
                        "conceptos": g["conceptos"],
                        "codigo_mayor": g["codigo_mayor"],
                    }
                )

    if duplicados:
        logger.warning(
            "  OJO: %d líneas de detalle duplicadas se saltaron (archivos repetidos).", duplicados
        )

    if headers_base is None:
        raise ValueError("No se encontró ningún archivo DETALLE con datos.")
    return headers_base + ["OBSERVACION FINAL"], filas, glosados


def consolidar_facturas(archivos: list[Path]) -> tuple[list[str], list[list]]:
    headers_base: list[str] | None = None
    filas: list[list] = []
    vistas: set = set()
    for arch in archivos:
        headers, rows = leer_xlsx(arch)
        if not rows:
            continue
        if headers_base is None:
            headers_base = headers
        rows = alinear_filas(headers, rows, headers_base, arch.name)
        for row in rows:
            clave = tuple(norm_texto(c) for c in row)
            if clave in vistas:
                continue
            vistas.add(clave)
            filas.append(list(row))
    if headers_base is None:
        raise ValueError("No se encontró ningún archivo de FACTURAS con datos.")
    return headers_base, filas


def _iterar_base(path: Path) -> Iterator[list]:
    """Itera las filas de la base DGH (xlsx/csv/txt) en streaming, sin
    materializarla: la base real pesa 80MB+ y cargarla entera agota la RAM.
    La primera fila que produce es el encabezado."""
    if path.suffix.lower() in {".csv", ".txt"}:
        import csv as _csv

        with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            muestra = fh.read(4096)
            fh.seek(0)
            try:
                dialecto = _csv.Sniffer().sniff(muestra, delimiters=";,\t|")
            except _csv.Error:
                dialecto = _csv.excel
            for row in _csv.reader(fh, dialecto):
                yield list(row)
    else:
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            raise ValueError(f"No se pudo leer la base DGH '{path.name}': {exc}") from exc
        try:
            ws = wb.active
            ws.reset_dimensions()
            for row in ws.iter_rows(values_only=True):
                yield list(row)
        finally:
            wb.close()


def cargar_base_dgh(
    path: Path, facturas_trabajadas: set[str]
) -> tuple[list[list], dict[tuple[str, str], str]]:
    """Lee la base DGH en streaming, filtra las facturas trabajadas y la "arregla".

    El arreglo (igual al proceso manual): en las filas de medicamentos, que
    vienen con SLNSERPRO_SERVICIO vacío, se rellenan SERVICIO/CUPS y sus
    descripciones con CODIGO_MEDICAMENTO / NOMBRE_MEDICAMENTO.

    Devuelve:
      - filas para SERVICIOS FACTURADOS (solo COLS_SERVICIOS, ya arregladas)
      - cruce[(factura_norm, codigo_norm)] = código DGH del servicio (SLNSERPRO)
    """
    logger.info("Leyendo base DGH: %s (puede tardar si pesa mucho)...", path)

    it = _iterar_base(path)
    headers = [norm_texto(h) for h in next(it, [])]
    mapa = {norm_header(h): i for i, h in enumerate(headers)}

    def col(nombre: str) -> int | None:
        return mapa.get(norm_header(nombre))

    idx_fact = col("FACTURA")
    if idx_fact is None:
        raise ValueError(f"Base DGH: no se encontró la columna FACTURA. Encabezados: {headers}")
    idx_srv = col("SLNSERPRO_SERVICIO")
    idx_cups = col("SLNSERPRO_CUPS")
    idx_cod_med = col("CODIGO_MEDICAMENTO")
    idx_cod_med_fact = col("COD_MED_FACTURA")
    idx_nom_med = col("NOMBRE_MEDICAMENTO")

    idx_salida = [col(c) for c in COLS_SERVICIOS]
    for c, pos in zip(COLS_SERVICIOS, idx_salida):
        if pos is None:
            logger.warning("Base DGH: falta la columna '%s' (saldrá vacía).", c)

    def celda(row: list, i: int | None) -> str:
        return norm_texto(row[i]) if i is not None and i < len(row) else ""

    filas_filtradas: list[list] = []
    cruce: dict[tuple[str, str], str] = {}
    total = 0
    for row in it:
        total += 1
        if row is None or all(c is None or norm_texto(c) == "" for c in row):
            continue
        fact = norm_factura(celda(row, idx_fact))
        if fact not in facturas_trabajadas:
            continue

        servicio = norm_codigo(celda(row, idx_srv))
        cod_med = norm_codigo(celda(row, idx_cod_med))
        nom_med = celda(row, idx_nom_med)

        # --- Arreglo: medicamentos rellenan las columnas de servicio ---
        valores = {}
        for c, i in zip(COLS_SERVICIOS, idx_salida):
            v = celda(row, i)
            valores[c] = norm_codigo(v) if c in COLS_SERVICIOS_CODIGO else v
        if not servicio and cod_med:
            valores["SLNSERPRO_SERVICIO"] = cod_med
            valores["DESCRIPCION INSTITUCIONAL"] = nom_med
            valores["SLNSERPRO_CUPS"] = cod_med
            valores["DESCRIPCION CUPS"] = nom_med
        filas_filtradas.append([valores[c] for c in COLS_SERVICIOS])

        # --- Cruce: cualquier código conocido de la fila -> código DGH efectivo ---
        slnserpro = valores["SLNSERPRO_SERVICIO"]
        if slnserpro:
            for i in (idx_srv, idx_cups, idx_cod_med, idx_cod_med_fact):
                cod = norm_codigo(celda(row, i))
                if cod:
                    cruce.setdefault((fact, cod), slnserpro)

    logger.info(
        "Base DGH: %d filas leídas · %d de las %d facturas trabajadas.",
        total,
        len(filas_filtradas),
        len(facturas_trabajadas),
    )
    return filas_filtradas, cruce


def generar_objeciones(
    glosados: list[dict],
    fecha: datetime,
    cruce: dict[tuple[str, str], str] | None,
) -> tuple[list[list], list[list]]:
    """Arma las filas del archivo de OBJECIONES (una por servicio glosado).

    Devuelve (filas_objeciones, filas_no_cruzadas).
    """
    filas: list[list] = []
    no_cruzados: list[list] = []
    malformadas: set[str] = set()
    consecutivo = 0
    factura_actual: str | None = None

    # CROTIPOBJ se clasifica por FACTURA completa: si la factura tiene glosas
    # CL y de otros conceptos, TODAS sus filas van con 2 (mixta); solo CL -> 1
    # en todas; sin CL -> 0 en todas.
    conceptos_factura: dict[str, set] = {}
    for srv in glosados:
        conceptos_factura.setdefault(norm_factura(srv["factura"]), set()).update(srv["conceptos"])

    for srv in glosados:
        fact = srv["factura"]
        if fact != factura_actual:
            consecutivo += 1
            factura_actual = fact
        if _num_factura(fact) is None:
            malformadas.add(fact)

        # SLNSERPRO: el codigo_servicio del DETALLE; si hay base DGH y la fila
        # cruza, manda el código DGH (que puede traer sufijo H). Si hay base y
        # NO cruza, se deja el del detalle y se reporta en NO_CRUZADOS.
        slnserpro = norm_codigo(srv["codigo_servicio"]) or None
        if cruce is not None:
            del_dgh = cruce.get((norm_factura(fact), norm_codigo(srv["codigo_servicio"])))
            if del_dgh:
                slnserpro = del_dgh
            else:
                no_cruzados.append(
                    [
                        factura_dgh(fact),
                        srv["id_detalle"],
                        srv["codigo_servicio"],
                        srv["observacion"][:100],
                    ]
                )

        conceptos = conceptos_factura[norm_factura(fact)]
        tiene_cl = "CL" in conceptos
        otros = bool(conceptos - {"CL"})
        tipo = 2 if (tiene_cl and otros) else (1 if tiene_cl else 0)

        filas.append(
            [
                str(consecutivo),  # CDCONSEC (texto, como en la plantilla)
                fecha,  # CDFECDOC (fecha Excel)
                factura_dgh(fact),  # CRNCXC   (HUS0000496207)
                fecha,  # CROFECOBJ
                None,  # CROREFERE
                None,  # CROOBSERV
                0,  # CROCLAOBJ
                None,  # CRNCLAOBJ
                "999",  # GENUSUARIO4 (texto)
                srv["codigo_mayor"],  # CRNCONOBJ (código completo: TA2901...)
                slnserpro,  # SLNSERPRO
                None,  # IDRIPS
                None,  # CTNCENCOS
                srv["valor_glosado"],  # CROVALOBJ (número)
                srv["observacion"],  # CRDOBSERV
                tipo,  # CROTIPOBJ
            ]
        )

    if malformadas:
        logger.warning(
            "OJO: %d factura(s) no siguen el patrón HUS y salen tal cual en CRNCXC: %s",
            len(malformadas),
            ", ".join(sorted(malformadas)[:5]),
        )
    return filas, no_cruzados


# --------------------------------------------------------------------------- main
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Consolida GLOSAS/DETALLES/FACTURAS de COOSALUD y genera el archivo de OBJECIONES (DGH).",
    )
    p.add_argument(
        "--carpeta",
        required=True,
        help='Carpeta organizada (la "CARGUE MASIVO COOSALUD" que crea el organizador).',
    )
    p.add_argument(
        "--fecha",
        required=True,
        help="Fecha del día que se revisa, DD/MM/AAAA (ej: 04/07/2026). Va en CDFECDOC y CROFECOBJ.",
    )
    p.add_argument(
        "--servicios",
        default=None,
        help="Base DGH de servicios facturados (xlsx/csv/txt) para el punto 4 y el cruce SLNSERPRO.",
    )
    p.add_argument(
        "--salida",
        default=None,
        help=f"Carpeta de salida. Def: <carpeta>\\{SALIDA_DEFECTO}",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Log detallado.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    try:
        fecha = datetime.strptime(args.fecha, "%d/%m/%Y")
    except ValueError:
        logger.error(
            "ERROR: --fecha debe ser DD/MM/AAAA (ej: 04/07/2026). Recibido: %s", args.fecha
        )
        return 1

    carpeta = Path(args.carpeta)
    if not carpeta.is_dir():
        logger.error("ERROR: no existe la carpeta %s", carpeta)
        return 1
    salida = Path(args.salida) if args.salida else carpeta / SALIDA_DEFECTO
    salida.mkdir(parents=True, exist_ok=True)

    arch_glosas = buscar_archivos(carpeta, CARPETA_GLOSAS, "*.xlsx")
    arch_detalles = buscar_archivos(carpeta, CARPETA_DETALLES, "*.xlsx")
    arch_facturas = buscar_archivos(carpeta, CARPETA_FACTURAS, "*.xlsx")
    logger.info(
        "Archivos: %d GLOSAS · %d DETALLES · %d FACTURAS",
        len(arch_glosas),
        len(arch_detalles),
        len(arch_facturas),
    )
    if not arch_glosas or not arch_detalles:
        logger.error("ERROR: faltan archivos en GLOSAS o DETALLES dentro de %s", carpeta)
        return 1

    try:
        # --- Puntos 2 y 3: consolidados + observación final -------------------
        logger.info("\n[1/4] Consolidando GLOSAS...")
        h_glosas, f_glosas, agrupado = consolidar_glosas(arch_glosas)
        logger.info("  %d glosas · %d id_detalle distintos", len(f_glosas), len(agrupado))

        logger.info("[2/4] Consolidando DETALLES (+ OBSERVACION FINAL)...")
        h_det, f_det, glosados = consolidar_detalles(arch_detalles, agrupado)
        logger.info("  %d líneas de detalle · %d servicios glosados", len(f_det), len(glosados))

        logger.info("[3/4] Consolidando FACTURAS...")
        h_fact, f_fact = consolidar_facturas(arch_facturas) if arch_facturas else ([], [])
        logger.info("  %d facturas", len(f_fact))

        # Glosas cuyo id_detalle no apareció en ningún DETALLE (avisar, no perder).
        ids_detalle = {g["id_detalle"] for g in glosados}
        huerfanas = [k for k in agrupado if k not in ids_detalle]
        if huerfanas:
            logger.warning(
                "OJO: %d id_detalle con glosas NO aparecen en los DETALLE (ej: %s)",
                len(huerfanas),
                ", ".join(huerfanas[:5]),
            )

        # --- Punto 4: base DGH filtrada y arreglada ----------------------------
        cruce = None
        f_serv: list[list] = []
        if args.servicios:
            facturas_trabajadas = {norm_factura(s["factura"]) for s in glosados}
            f_serv, cruce = cargar_base_dgh(Path(args.servicios), facturas_trabajadas)

        # --- Punto 5: archivo de objeciones ------------------------------------
        logger.info("[4/4] Generando OBJECIONES...")
        f_obj, no_cruzados = generar_objeciones(glosados, fecha, cruce)
        n_facturas_obj = int(f_obj[-1][0]) if f_obj else 0
        logger.info("  %d filas de objeciones · %d facturas", len(f_obj), n_facturas_obj)
        if no_cruzados:
            logger.warning(
                "  %d servicios NO cruzaron con la base DGH (hoja NO_CRUZADOS)", len(no_cruzados)
            )

        # --- Escritura ---------------------------------------------------------
        logger.info("\nEscribiendo archivos en %s ...", salida)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "GLOSAS"
        escribir_hoja(ws, h_glosas, f_glosas)
        ws2 = wb.create_sheet("AGRUPADO")
        escribir_hoja(
            ws2,
            ["id_detalle", "OBSERVACION FINAL"],
            [[k, v["observacion"]] for k, v in agrupado.items()],
        )
        wb.save(salida / "CONSOLIDADO GLOSAS.xlsx")

        wb = openpyxl.Workbook()
        wb.active.title = "DETALLE"
        escribir_hoja(wb.active, h_det, f_det)
        wb.save(salida / "CONSOLIDADO DETALLE.xlsx")

        if f_fact:
            wb = openpyxl.Workbook()
            wb.active.title = "FACTURAS"
            escribir_hoja(wb.active, h_fact, f_fact)
            wb.save(salida / "CONSOLIDADO FACTURAS.xlsx")

        if args.servicios:
            wb = openpyxl.Workbook()
            wb.active.title = "SERVICIOS"
            escribir_hoja(wb.active, COLS_SERVICIOS, f_serv)
            wb.save(salida / "SERVICIOS FACTURADOS COOSALUD.xlsx")

        wb = openpyxl.Workbook()
        wb.active.title = "OBJECIONES"
        escribir_hoja(
            wb.active,
            [c for c, _ in COLS_OBJECIONES],
            f_obj,
            formatos=[f for _, f in COLS_OBJECIONES],
        )
        if no_cruzados:
            ws_nc = wb.create_sheet("NO_CRUZADOS")
            escribir_hoja(
                ws_nc,
                ["factura", "id_detalle", "codigo_servicio", "observacion (inicio)"],
                no_cruzados,
            )
        wb.save(salida / "OBJECIONES.xlsx")

    except ValueError as exc:
        logger.error("ERROR: %s", exc)
        return 1

    logger.info("\n===== LISTO =====")
    logger.info("  CONSOLIDADO GLOSAS.xlsx            %d glosas (+hoja AGRUPADO)", len(f_glosas))
    logger.info("  CONSOLIDADO DETALLE.xlsx           %d líneas", len(f_det))
    if f_fact:
        logger.info("  CONSOLIDADO FACTURAS.xlsx          %d facturas", len(f_fact))
    if args.servicios:
        logger.info("  SERVICIOS FACTURADOS COOSALUD.xlsx %d filas", len(f_serv))
    logger.info(
        "  OBJECIONES.xlsx                    %d filas · %d facturas%s",
        len(f_obj),
        n_facturas_obj,
        f" · {len(no_cruzados)} sin cruce DGH" if no_cruzados else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
