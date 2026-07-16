"""organizar_objeciones_savia.py — Organiza las objeciones de SAVIA SALUD.

Toma el/los export(s) crudos del Dispensario (`OBJECIONES_DISPENSARIO_HUS*.xlsx`,
una fila por objeción, con las columnas técnicas CRNCXC / CRNCONOBJ / SLNSERPRO /
CROVALOBJ / CRDOBSERV) y arma un Excel LIMPIO con el formato exacto que usa el
equipo para trabajar las glosas de SAVIA SALUD:

    Numero_factura | Cod_Servicio | Servicio | Cantidad_Servicio |
    Valor_Unitario | Valor_Glosa | Motivo_Esp_Glosa_Valor_A | Observacion_Glosa_A

Es el mismo patrón que `convertir_tramite_masivo.py` (que convierte el export del
CRRP al formato de SIMED), pero apuntando al formato de SAVIA SALUD tomado como
plantilla del archivo `SAVIA_SALUD_8.03.xlsx`.

MAPEO DE CAMPOS (crudo → SAVIA):
    Numero_factura           ← CRNCXC          (HUS0000530265 → HUS530265)
    Cod_Servicio             ← SLNSERPRO       (21519H, 908337H, 20095751, …)
    Servicio                 ← se extrae del texto CRDOBSERV (nombre del servicio)
    Cantidad_Servicio        ← se extrae del texto ("SE FACTURA UNA UNIDAD" → 1)
    Valor_Unitario           ← se extrae del texto ("POR VALOR DE N PESOS") / Cantidad
    Valor_Glosa              ← CROVALOBJ        (valor objetado)
    Motivo_Esp_Glosa_Valor_A ← CRNCONOBJ       (CL0801 → CL08 en modo 'corto')
    Observacion_Glosa_A      ← CRDOBSERV        (texto limpio, sin el "$NNN" final)

CÓDIGO DE OBJECIÓN (--codigo):
    El Dispensario usa códigos de 6 caracteres: <GG><CC><SS> (grupo + concepto +
    consecutivo), p.ej. CL0801, TA0801, SO0801. La plantilla de SAVIA usa los 4
    primeros (grupo + concepto): CL08, TA08, SO08. Verificado con TA0801→TA08 y
    CL0801→CL08 (apoyo diagnóstico).
        corto    (default) → CL0801 → CL08   (coincide con la plantilla de SAVIA)
        completo          → CL0801 → CL0801  (código trazable del Dispensario)
    Además, con --mapa-codigos <archivo.json> se puede forzar un mapeo puntual
    {"CL0801": "CL06", ...} para los códigos que SAVIA espere distinto.

USO:
    # Un solo Excel del Dispensario
    py organizar_objeciones_savia.py \
        --entrada "OBJECIONES_DISPENSARIO_HUS0000530265.xlsx" \
        --salida  "SAVIA_SALUD_organizado.xlsx"

    # Varias facturas (una carpeta con muchos OBJECIONES_DISPENSARIO_*.xlsx)
    py organizar_objeciones_savia.py \
        --entrada "D:\\...\\OBJECIONES SAVIA" \
        --salida  "SAVIA_SALUD_organizado.xlsx"

INSTALACIÓN (una vez):
    py -m pip install openpyxl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("organizar_savia")


# ─── Encabezado de salida (formato SAVIA SALUD, tomado de SAVIA_SALUD_8.03.xlsx) ─

# (etiqueta, ancho de columna). El orden ES el orden de columnas del Excel.
ENCABEZADOS_SAVIA: tuple[tuple[str, int], ...] = (
    ("Numero_factura", 16),
    ("Cod_Servicio", 14),
    ("Servicio", 42),
    ("Cantidad_Servicio", 12),
    ("Valor_Unitario", 14),
    ("Valor_Glosa", 14),
    ("Motivo_Esp_Glosa_Valor_A", 14),
    ("Observacion_Glosa_A", 100),
)


# ─── Lectura del export crudo del Dispensario ────────────────────────────────


def _norm_header(h: object) -> str:
    """Normaliza un encabezado: mayúsculas, sin tildes, sin espacios de más."""
    s = unicodedata.normalize("NFKD", str(h or "").strip().upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


# Nombres de columna del export del Dispensario. Se buscan por nombre (tolerante
# a tildes/espacios); si no aparecen, se cae a los índices fijos observados.
COLUMNAS = {
    "factura": {"CRNCXC", "NUMERO FACTURA", "NUMERO_FACTURA", "FACTURA"},
    "concepto": {"CRNCONOBJ", "CONCEPTO", "CODIGO OBJECION", "COD OBJECION"},
    "cod_servicio": {"SLNSERPRO", "COD SERVICIO", "COD_SERVICIO", "CODIGO SERVICIO"},
    "valor": {"CROVALOBJ", "VALOR OBJETADO", "VALOR OBJECION", "VALOR GLOSA"},
    "observacion": {"CRDOBSERV", "OBSERVACION", "OBSERVACION GLOSA", "DETALLE"},
}
# Índices fijos de respaldo (según OBJECIONES_DISPENSARIO_HUS0000530265.xlsx).
IDX_FALLBACK = {
    "factura": 2,
    "concepto": 9,
    "cod_servicio": 10,
    "valor": 13,
    "observacion": 14,
}


def _resolver_columnas(headers: list[str]) -> dict[str, int]:
    """Devuelve {clave: indice} mapeando por nombre de encabezado; si una
    columna no se reconoce por nombre, usa el índice fijo de respaldo."""
    norm = [_norm_header(h) for h in headers]
    idx: dict[str, int] = {}
    for clave, alias in COLUMNAS.items():
        encontrado = next((i for i, h in enumerate(norm) if h in alias), None)
        if encontrado is None:
            encontrado = IDX_FALLBACK[clave]
            logger.debug(
                f"  columna '{clave}' no reconocida por nombre; uso índice fijo {encontrado}"
            )
        idx[clave] = encontrado
    return idx


def _cell(row: tuple, idx: dict[str, int], clave: str) -> object:
    """Valor de la columna `clave` en `row`, o None si el índice se sale de rango
    (filas cortas de la exportación)."""
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


# ─── Normalización de factura ────────────────────────────────────────────────

_RE_HUS_CORTO = re.compile(r"^([A-Za-z]+)0*(\d+)$")


def factura_corta(fac: object) -> str:
    """HUS0000530265 → HUS530265 (quita ceros de relleno). Mismo criterio que
    `radicar_facturacion.factura_corta`: algunos portales rechazan el formato
    largo. Si no matchea el patrón, devuelve el texto tal cual."""
    s = str(fac or "").strip()
    m = _RE_HUS_CORTO.match(s)
    return (m.group(1).upper() + m.group(2)) if m else s


# ─── Código de objeción (CRNCONOBJ → Motivo_Esp_Glosa_Valor_A) ───────────────


def codigo_savia(
    concepto: str,
    modo: str = "corto",
    mapa: dict[str, str] | None = None,
) -> str:
    """Deriva el código de objeción para SAVIA a partir del código del
    Dispensario.

    - Si `mapa` trae el código exacto, se usa ese (override manual).
    - modo 'corto'    → los 4 primeros caracteres (grupo+concepto): CL0801 → CL08.
    - modo 'completo' → el código tal cual del Dispensario: CL0801 → CL0801.
    """
    cod = (concepto or "").strip().upper()
    if mapa and cod in mapa:
        return mapa[cod]
    if modo == "completo":
        return cod
    # 'corto': grupo (2 letras) + concepto (2 dígitos). Robusto aunque venga con
    # separadores raros: tomo las 2 primeras letras y los 2 primeros dígitos.
    m = re.match(r"^([A-Za-z]{2})\D*(\d{2})", cod)
    if m:
        return (m.group(1) + m.group(2)).upper()
    return cod[:4]


# ─── Extracción desde el texto de la objeción (CRDOBSERV) ────────────────────

# Números escritos con palabra (el Dispensario suele decir "SE FACTURA UNA
# UNIDAD" en lugar de "1 UNIDAD").
_PALABRA_NUM = {
    "una": 1,
    "uno": 1,
    "un": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
}

_RE_CANTIDAD = re.compile(r"SE\s+FACTURA(?:N)?\s+([A-Za-zÁÉÍÓÚ]+|\d+)\s+UNIDAD", re.IGNORECASE)
_RE_VALOR_FACTURADO = re.compile(r"POR\s+VALOR\s+DE\s+\$?\s*([\d.,]+)\s*(?:PESOS)?", re.IGNORECASE)


def extraer_cantidad(texto: str) -> int:
    """Cantidad facturada: SE FACTURA UNA UNIDAD → 1, SE FACTURAN DOS → 2. Default 1."""
    m = _RE_CANTIDAD.search(texto or "")
    if not m:
        return 1
    token = m.group(1).strip().lower()
    if token.isdigit():
        return int(token) or 1
    token = "".join(c for c in unicodedata.normalize("NFKD", token) if not unicodedata.combining(c))
    return _PALABRA_NUM.get(token, 1)


def extraer_valor_unitario(texto: str, valor_glosa: int, cantidad: int) -> int:
    """Valor unitario facturado. Prioriza el "POR VALOR DE N PESOS" del texto;
    si no está, asume objeción de línea completa (facturado == objetado). En
    ambos casos divide por la cantidad para dar el valor por unidad."""
    cantidad = max(cantidad, 1)
    m = _RE_VALOR_FACTURADO.search(texto or "")
    base = _num(m.group(1)) if m else valor_glosa
    if base <= 0:
        base = valor_glosa
    return round(base / cantidad) if cantidad else base


def extraer_servicio(texto: str, cod_servicio: str, concepto: str) -> str:
    """Nombre del servicio glosado. Estrategias, en orden:
    1. Lo que sigue a "SE GLOSA CODIGO <cod_servicio>" hasta el primer punto,
       "SE FACTURA" o "VALOR A OBJETAR".
    2. El nombre del concepto del encabezado (después de "CALIDAD-"/"SOPORTES-"),
       útil para estancias que no traen código de servicio.
    3. Cadena vacía si no se puede determinar.
    """
    t = texto or ""
    if cod_servicio:
        cod_esc = re.escape(str(cod_servicio).strip())
        m = re.search(
            rf"SE\s+GLOSA\s+C[OÓ]DIGO\s+{cod_esc}\s*(.+?)"
            r"(?:\.|\bSE\s+FACTURA|\bVALOR\s+A\s+OBJETAR|$)",
            t,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            nombre = " ".join(m.group(1).split()).strip(" .-")
            if nombre:
                return nombre
    # Fallback: nombre del concepto del encabezado ("CL0101 CALIDAD-ESTANCIA …").
    cod_obj = re.escape((concepto or "").strip())
    m = re.match(
        rf"\s*{cod_obj}\s+[A-Za-zÁÉÍÓÚ]+\s*-\s*(.+?)"
        r"(?:\s+-\s+|\s*:\s|\bEL\s+CARGO|\bLOS\s+CARGOS|\bEXISTE\b|$)",
        t,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        nombre = " ".join(m.group(1).split()).strip(" .-")
        if nombre:
            return nombre
    return ""


_RE_VALOR_PEGADO = re.compile(r"\s*\$\s*[\d.,]+\s*$")
# Sólo el token de código del inicio ("CL0801 "). Es lo único que se puede quitar
# sin ambigüedad: el nombre del concepto que le sigue ("CALIDAD-APOYO
# DIAGNÓSTICO") a veces se separa del texto con " - " y a veces se pega directo
# a la redacción, así que no se toca para no cortar la justificación.
_RE_ENCABEZADO_COD = re.compile(r"^\s*[A-Za-z]{2}\d{2,6}\s+", re.IGNORECASE)


def limpiar_observacion(texto: str, limpiar_encabezado: bool = False) -> str:
    """Limpia el texto de la objeción para la columna Observacion_Glosa_A:
    - quita el "$NNNNN" que el Dispensario pega al final del texto,
    - normaliza espacios,
    - (opcional) quita el código del inicio ("CL0801 "), que ya va en su propia
      columna Motivo_Esp_Glosa_Valor_A."""
    t = (texto or "").strip()
    t = _RE_VALOR_PEGADO.sub("", t)
    if limpiar_encabezado:
        t = _RE_ENCABEZADO_COD.sub("", t, count=1)
    return " ".join(t.split()).strip()


# ─── Lectura + transformación ────────────────────────────────────────────────


def _iter_archivos(entradas: list[Path]) -> list[Path]:
    """Expande carpetas a sus *.xlsx y valida que existan. Ignora los temporales
    de Excel (~$...) y evita duplicados preservando el orden."""
    vistos: set[Path] = set()
    archivos: list[Path] = []
    for e in entradas:
        candidatos: list[Path]
        if e.is_dir():
            candidatos = sorted(p for p in e.glob("*.xlsx") if not p.name.startswith("~$"))
            if not candidatos:
                logger.warning(f"  carpeta sin .xlsx: {e}")
        elif e.is_file():
            candidatos = [e]
        else:
            logger.error(f"  no existe: {e}")
            continue
        for p in candidatos:
            rp = p.resolve()
            if rp not in vistos:
                vistos.add(rp)
                archivos.append(p)
    return archivos


def leer_objeciones(
    ruta: Path,
    modo_codigo: str,
    mapa_codigos: dict[str, str] | None,
    limpiar_encabezado: bool,
    normalizar_factura: bool,
) -> list[dict]:
    """Lee un Excel del Dispensario y devuelve una lista de dicts, uno por
    objeción, ya con el formato de columnas de SAVIA."""
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

    objeciones: list[dict] = []
    for r in filas:
        if r is None:
            continue

        factura_raw = str(_cell(r, idx, "factura") or "").strip()
        observacion_raw = str(_cell(r, idx, "observacion") or "").strip()
        # Fila sin factura ni texto: basura de la exportación, se salta.
        if not factura_raw and not observacion_raw:
            continue

        concepto = str(_cell(r, idx, "concepto") or "").strip()
        cod_servicio = str(_cell(r, idx, "cod_servicio") or "").strip()
        valor_glosa = _num(_cell(r, idx, "valor"))
        cantidad = extraer_cantidad(observacion_raw)

        objeciones.append(
            {
                "Numero_factura": factura_corta(factura_raw) if normalizar_factura else factura_raw,
                "Cod_Servicio": cod_servicio,
                "Servicio": extraer_servicio(observacion_raw, cod_servicio, concepto),
                "Cantidad_Servicio": cantidad,
                "Valor_Unitario": extraer_valor_unitario(observacion_raw, valor_glosa, cantidad),
                "Valor_Glosa": valor_glosa,
                "Motivo_Esp_Glosa_Valor_A": codigo_savia(concepto, modo_codigo, mapa_codigos),
                "Observacion_Glosa_A": limpiar_observacion(observacion_raw, limpiar_encabezado),
            }
        )
    wb.close()
    return objeciones


# ─── Escritura del Excel de salida ───────────────────────────────────────────


def escribir_savia(objeciones: list[dict], salida: Path) -> None:
    """Escribe el Excel organizado con el formato/estilo de SAVIA SALUD."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "SAVIA SALUD"

    fill_hdr = PatternFill("solid", fgColor="1F4E78")
    font_hdr = Font(bold=True, color="FFFFFF")
    for col, (etiqueta, ancho) in enumerate(ENCABEZADOS_SAVIA, start=1):
        c = ws.cell(row=1, column=col, value=etiqueta)
        c.fill = fill_hdr
        c.font = font_hdr
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = ancho

    columnas = [etq for etq, _ in ENCABEZADOS_SAVIA]
    num_cols = {"Cantidad_Servicio", "Valor_Unitario", "Valor_Glosa"}
    fila = 2
    for obj in objeciones:
        for col, nombre in enumerate(columnas, start=1):
            celda = ws.cell(row=fila, column=col, value=obj.get(nombre))
            if nombre in num_cols:
                celda.number_format = "#,##0"
            elif nombre == "Observacion_Glosa_A":
                celda.alignment = Alignment(wrap_text=True, vertical="top")
        fila += 1

    ws.freeze_panes = "A2"
    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(salida))


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
        logger.error('El mapa de códigos debe ser un objeto JSON {"CL0801": "CL08", ...}')
        sys.exit(2)
    return {str(k).strip().upper(): str(v).strip() for k, v in data.items()}


def _resumen(objeciones: list[dict]) -> None:
    facturas = defaultdict(int)
    codigos = defaultdict(int)
    total_glosa = 0
    for o in objeciones:
        facturas[o["Numero_factura"]] += 1
        codigos[o["Motivo_Esp_Glosa_Valor_A"]] += 1
        total_glosa += o["Valor_Glosa"]
    logger.info(f"  Facturas: {len(facturas)}  |  Objeciones: {len(objeciones)}")
    logger.info(f"  Valor glosado total: ${total_glosa:,.0f}")
    logger.info("  Códigos de objeción:")
    for cod, n in sorted(codigos.items(), key=lambda kv: (-kv[1], kv[0])):
        logger.info(f"    {cod or '(sin código)'}: {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--entrada",
        type=Path,
        nargs="+",
        required=True,
        help="Uno o más Excel del Dispensario, o carpeta(s) con OBJECIONES_DISPENSARIO_*.xlsx.",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        required=True,
        help="Excel destino con el formato organizado de SAVIA SALUD.",
    )
    parser.add_argument(
        "--codigo",
        choices=("corto", "completo"),
        default="corto",
        help="corto (default): CL0801 → CL08 (plantilla SAVIA). completo: CL0801 tal cual.",
    )
    parser.add_argument(
        "--mapa-codigos",
        type=Path,
        default=None,
        help='JSON opcional para forzar códigos: {"CL0801": "CL06", ...}.',
    )
    parser.add_argument(
        "--limpiar-encabezado",
        action="store_true",
        help="Quita el encabezado 'CL0801 CALIDAD-... - ' del texto de la observación.",
    )
    parser.add_argument(
        "--sin-normalizar-factura",
        action="store_true",
        help="Deja la factura tal cual (HUS0000530265) en vez de acortarla (HUS530265).",
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

    archivos = _iter_archivos(args.entrada)
    if not archivos:
        logger.error("No hay archivos de entrada válidos.")
        return 1

    mapa = _cargar_mapa(args.mapa_codigos)
    logger.info(f"Leyendo {len(archivos)} archivo(s) del Dispensario…")
    todas: list[dict] = []
    for arch in archivos:
        objs = leer_objeciones(
            arch,
            modo_codigo=args.codigo,
            mapa_codigos=mapa,
            limpiar_encabezado=args.limpiar_encabezado,
            normalizar_factura=not args.sin_normalizar_factura,
        )
        logger.info(f"  {arch.name}: {len(objs)} objeciones")
        todas.extend(objs)

    if not todas:
        logger.error("No se encontró ninguna objeción en los archivos de entrada.")
        return 1

    # Consolidar agrupando por factura, preservando el orden de aparición.
    todas.sort(key=lambda o: o["Numero_factura"])
    escribir_savia(todas, args.salida)

    logger.info(f"\nExcel organizado: {args.salida}")
    _resumen(todas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
