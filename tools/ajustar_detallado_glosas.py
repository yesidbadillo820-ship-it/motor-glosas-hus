"""ajustar_detallado_glosas.py — deja el detallado de factura SOLO con lo que
la entidad sigue glosando.

Automatiza el trabajo manual de depurar los "detallados de factura" antes de
armar la respuesta a la entidad. En una sola corrida:

  1. Lee el **consolidado** de facturas a trabajar y le **quita los duplicados**.
  2. Abre el **Excel del detallado** (el que baja el sistema con una hoja por
     factura, que trae más facturas de las que se van a trabajar) y **borra las
     hojas de las facturas que no están en el consolidado**.
  3. En cada hoja que queda: **quita el encabezado institucional** (logo, dirección,
     NIT, ciudad, QR, CUFE, "Página 1/1") y cambia el título
     "FACTURA ELECTRONICA DE" por **"DETALLADO DE FACTURA"**.
  4. Cruza cada ítem contra el **ReporteGlosasReclamPAQUETE NNNNN.xlsx** (lo que
     la entidad aprobó vs. lo que sigue glosando) y:
       - **quita** los ítems que la entidad ya aprobó (valor glosado = 0),
       - **ajusta** cantidad y valor de los ítems aprobados a medias (queda solo
         la parte que sigue glosada),
       - **deja igual** los ítems glosados en su totalidad.
  5. Borra los títulos de grupo que quedaron sin ítems (CONSULTAS MEDICAS,
     MEDICAMENTOS POS, DERECHOS DE SALA, …), **recalcula el subtotal y el total**
     y escribe el **total en letras**.
  6. Escribe el Excel corregido y una **bitácora CSV** ítem por ítem con lo que
     hizo (y con lo que NO pudo cruzar, para revisión del auditor).

IMPORTANTE — el reporte de glosas trae el MISMO ítem repartido en varias filas
(ej. VENDA DE GASA en una fila por 4 unidades y otra por 2). El bot **suma todas
las filas del ítem** antes de decidir. Revisar solo una fila subestima lo que
sigue glosado, que es el error típico del proceso manual.

USO (Windows, desde C:\\temp-notas):

    REM 1) Ver qué encontró, sin escribir nada (recomendado la primera vez):
    py tools\\ajustar_detallado_glosas.py ^
        --consolidado "D:\\USUARIO CARTERA\\Downloads\\CONSOLIDADO.xlsx" ^
        --detallado   "D:\\USUARIO CARTERA\\Downloads\\DETALLADOS PAQUETE 31068.xlsx" ^
        --reporte-glosas "D:\\USUARIO CARTERA\\Downloads\\ReporteGlosasReclamPAQUETE 31068.xlsx" ^
        --diagnostico

    REM 2) Generar el Excel corregido + la bitácora:
    py tools\\ajustar_detallado_glosas.py ^
        --consolidado "D:\\USUARIO CARTERA\\Downloads\\CONSOLIDADO.xlsx" ^
        --detallado   "D:\\USUARIO CARTERA\\Downloads\\DETALLADOS PAQUETE 31068.xlsx" ^
        --reporte-glosas "D:\\USUARIO CARTERA\\Downloads\\ReporteGlosasReclamPAQUETE 31068.xlsx" ^
        --salida      "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\DETALLADOS_31068_AJUSTADO.xlsx" ^
        --reporte-csv "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\bitacora_31068.csv"

Seguro por defecto: NO toca los archivos originales. Solo los lee y escribe el
Excel de salida y la bitácora CSV.

Requiere: py -m pip install openpyxl   (opcional: Pillow, para conservar
imágenes que estén FUERA del encabezado; las del encabezado se eliminan igual).
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Reutilizamos la normalización de factura del radicador (mismo tools/), para
# que el cruce por número de factura sea idéntico en todo el proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # pragma: no cover - camino normal
    from radicar_facturacion import normalizar_factura
except Exception:  # pragma: no cover - fallback si se ejecuta aislado

    def normalizar_factura(fac: str) -> str:
        f = (fac or "").strip().upper()
        f = re.sub(r"^HUS", "", f)
        return f.lstrip("0") or "0"


logger = logging.getLogger("ajustar_detallado")

# ─── Marcas del formato del detallado ────────────────────────────────────────

TITULO_ORIGINAL = "FACTURA ELECTRONICA DE"
TITULO_NUEVO = "DETALLADO DE FACTURA"

MARCA_SUBTOTAL = "VALOR SUBTOTAL DE SERVICIOS PRESTADOS"
MARCA_COPAGO = "VALOR CUOTA COPAGO"
MARCA_ANTICIPO = "VALOR ANTICIPO PAGADO POR EL USUARIO"
MARCA_COPAGO_USUARIO = "VALOR CUOTA DE COPAGO Y/O CUOTA MODERADORA ASUMIDA POR EL USUARIO"
MARCA_TOTAL_ORDEN = "VALOR TOTAL ORDEN DE SERVICIO"
MARCA_TOTAL_LETRAS = "TOTAL:"

# Encabezados de la tabla de ítems del detallado (tolerante a variantes).
_ALIAS_COL_ITEM: dict[str, tuple[str, ...]] = {
    "codigo": ("CODIGO", "COD", "COD.", "CODIGO SERVICIO"),
    "nombre": ("NOMBRE", "DESCRIPCION", "SERVICIO", "CONCEPTO"),
    "cantidad": ("CANT", "CANT.", "CANTIDAD"),
    "vr_unit": ("VR UNIT", "VR. UNIT", "VALOR UNITARIO", "VR UNITARIO"),
    "vr_pac": ("VR PAC", "VR. PAC", "VALOR PACIENTE"),
    "vr_ent": ("VR ENT", "VR. ENT", "VALOR ENTIDAD", "VR ENTIDAD"),
}

# Encabezados del ReporteGlosasReclamPAQUETE (tolerante a variantes/tildes).
_ALIAS_COL_GLOSA: dict[str, tuple[str, ...]] = {
    "factura": ("NUMERO FACTURA", "NUM FACTURA", "NRO FACTURA", "FACTURA", "NO FACTURA"),
    "radicacion": ("NUMERO RADICACION", "NUM RADICACION", "RADICACION"),
    "paquete": ("NUMERO PAQUETE", "NUM PAQUETE", "PAQUETE"),
    "consecutivo": ("CONSECUTIVO ITEM", "CONSECUTIVO"),
    "tipo_elemento": ("TIPO ELEMENTO", "TIPO DE ELEMENTO"),
    "codigo": ("COD ELEMENTO", "CODIGO ELEMENTO", "COD. ELEMENTO"),
    "descripcion": ("DESCRIPCION ELEMENTO", "DESCRIPCION DEL ELEMENTO"),
    "cant_reclamada": ("CANTIDAD RECLAMADO", "CANTIDAD RECLAMADA", "CANT RECLAMADO"),
    "valor_reclamado": ("VALOR RECLAMADO", "VLR RECLAMADO"),
    "cant_aprobada": ("CANTIDAD APROBADA", "CANTIDAD APROBADO", "CANT APROBADA"),
    "valor_aprobado": ("VALOR APROBADO", "VLR APROBADO"),
    "valor_glosado": ("VALOR GLOSADO", "VLR GLOSADO"),
    "descripcion_glosa": ("DESCRIPCION GLOSA", "DESCRIPCION DE GLOSA"),
    "anotacion": ("DESCRIPCION ANOTACION", "ANOTACION", "OBSERVACION"),
}

# Encabezados aceptados para la columna de factura del consolidado.
_ALIAS_FACTURA_CONSOLIDADO = (
    "FACTURA",
    "NUMERO FACTURA",
    "NUM FACTURA",
    "NRO FACTURA",
    "NO FACTURA",
    "FACTURA HUS",
    "NUMERO DE FACTURA",
    "NO. FACTURA",
)

_RE_FACTURA = re.compile(r"HUS\s?0*\d{4,12}", re.IGNORECASE)

# Tolerancia en pesos al comparar valores (redondeos del portal).
TOLERANCIA_PESOS = 1.0


# ─── Normalización ───────────────────────────────────────────────────────────


def _norm(s) -> str:
    """Mayúsculas, sin tildes, espacios colapsados."""
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return " ".join(s.split())


def _norm_desc(s) -> str:
    """Clave para comparar descripciones: sin tildes, sin puntuación."""
    t = _norm(s)
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    return " ".join(t.split())


def _norm_codigo(s) -> str:
    """Clave para comparar códigos: sin espacios ni puntos, en mayúsculas."""
    t = _norm(s)
    t = re.sub(r"[\s.]+", "", t)
    return t


def _parse_valor(v) -> float:
    """'$ 85.800,00' → 85800.0. Vacío o basura → 0.0."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if not t:
        return 0.0
    t = t.replace("$", "").replace(" ", "").replace("\u00a0", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")  # 1.234.567,89
    elif "," in t:
        ent, _, dec = t.partition(",")
        t = f"{ent.replace('.', '')}.{dec}" if len(dec) in (1, 2) else t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")  # 1.234.567
    elif "." in t:
        ent, _, dec = t.partition(".")
        if len(dec) == 3:  # 56.400 son miles, no decimales
            t = ent + dec
    try:
        n = float(t)
    except ValueError:
        return 0.0
    return -n if neg else n


# ─── Total en letras ─────────────────────────────────────────────────────────

_UNI = (
    "",
    "UNO",
    "DOS",
    "TRES",
    "CUATRO",
    "CINCO",
    "SEIS",
    "SIETE",
    "OCHO",
    "NUEVE",
    "DIEZ",
    "ONCE",
    "DOCE",
    "TRECE",
    "CATORCE",
    "QUINCE",
    "DIECISEIS",
    "DIECISIETE",
    "DIECIOCHO",
    "DIECINUEVE",
    "VEINTE",
    "VEINTIUNO",
    "VEINTIDOS",
    "VEINTITRES",
    "VEINTICUATRO",
    "VEINTICINCO",
    "VEINTISEIS",
    "VEINTISIETE",
    "VEINTIOCHO",
    "VEINTINUEVE",
)
_DEC = ("", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
_CEN = (
    "",
    "CIENTO",
    "DOSCIENTOS",
    "TRESCIENTOS",
    "CUATROCIENTOS",
    "QUINIENTOS",
    "SEISCIENTOS",
    "SETECIENTOS",
    "OCHOCIENTOS",
    "NOVECIENTOS",
)


def _letras_999(n: int, apocope: bool = False) -> str:
    if n <= 0:
        return ""
    if n == 100:
        return "CIEN"
    c, r = divmod(n, 100)
    partes = [_CEN[c]] if c else []
    if r:
        if r < 30:
            partes.append(_UNI[r])
        else:
            d, u = divmod(r, 10)
            partes.append(_DEC[d] + (" Y " + _UNI[u] if u else ""))
    out = " ".join(p for p in partes if p)
    if apocope:
        out = re.sub(r"\bVEINTIUNO$", "VEINTIUN", out)
        out = re.sub(r"\bUNO$", "UN", out)
    return out


def _letras_miles(n: int, apocope: bool = False) -> str:
    miles, uni = divmod(n, 1000)
    partes = []
    if miles == 1:
        partes.append("MIL")
    elif miles:
        partes.append(_letras_999(miles, apocope=True) + " MIL")
    if uni:
        partes.append(_letras_999(uni, apocope=apocope))
    return " ".join(p for p in partes if p)


def numero_a_letras(valor: float) -> str:
    """95200 → 'NOVENTA Y CINCO MIL DOSCIENTOS PESOS M/CTE'."""
    n = int(round(abs(_parse_valor(valor))))
    if n == 0:
        return "CERO PESOS M/CTE"
    millones, resto = divmod(n, 1_000_000)
    partes = []
    if millones == 1:
        partes.append("UN MILLON")
    elif millones:
        partes.append(_letras_miles(millones, apocope=True) + " MILLONES")
    if resto:
        partes.append(_letras_miles(resto))
    return " ".join(p for p in partes if p) + " PESOS M/CTE"


# ─── Modelo ──────────────────────────────────────────────────────────────────


@dataclass
class FilaGlosa:
    """Una fila del ReporteGlosasReclamPAQUETE."""

    factura: str
    codigo: str
    descripcion: str
    tipo_elemento: str = ""
    cant_reclamada: float = 0.0
    valor_reclamado: float = 0.0
    cant_aprobada: float = 0.0
    valor_aprobado: float = 0.0
    valor_glosado: float = 0.0
    descripcion_glosa: str = ""
    anotacion: str = ""
    usada: bool = False

    @property
    def vr_unit(self) -> float:
        return self.valor_reclamado / self.cant_reclamada if self.cant_reclamada else 0.0


@dataclass
class ItemDetallado:
    """Un ítem (servicio/insumo) dentro de la hoja del detallado."""

    fila: int
    filas: list[int]  # la fila del ítem + las de continuación del nombre
    grupo: str
    codigo: str
    nombre: str
    cantidad: float
    vr_unit: float
    vr_pac: float
    vr_ent: float


@dataclass
class Bloque:
    """Un grupo del detallado (CONSULTAS MEDICAS, MATERIALES E INSUMOS, …)."""

    titulo: str
    fila_titulo: int | None
    fila_fin: int
    items: list[ItemDetallado] = field(default_factory=list)


@dataclass
class ResultadoItem:
    factura: str
    hoja: str
    grupo: str
    codigo: str
    nombre: str
    cant_orig: float
    vr_ent_orig: float
    valor_reclamado: float = 0.0
    valor_aprobado: float = 0.0
    valor_glosado: float = 0.0
    accion: str = ""  # QUITADO | AJUSTADO | CONSERVADO | SIN_CRUCE
    cant_nueva: float = 0.0
    vr_ent_nuevo: float = 0.0
    cruce: str = ""  # codigo | descripcion | valor_unitario | (vacío)
    filas_reporte: int = 0
    observacion: str = ""


@dataclass
class ResultadoHoja:
    hoja: str
    factura: str
    estado: str  # AJUSTADA | ELIMINADA | SIN_GLOSAS | SIN_ESTRUCTURA
    items_total: int = 0
    items_quitados: int = 0
    items_ajustados: int = 0
    items_conservados: int = 0
    items_sin_cruce: int = 0
    subtotal_antes: float = 0.0
    subtotal_despues: float = 0.0
    detalle: list[ResultadoItem] = field(default_factory=list)
    observacion: str = ""


# ─── Lectura de tablas ───────────────────────────────────────────────────────


def _abrir_libro(ruta: Path, *, solo_datos: bool = True, solo_lectura: bool = False):
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - depende del entorno
        raise SystemExit("Falta openpyxl. Instalalo con:  py -m pip install openpyxl") from None
    return openpyxl.load_workbook(ruta, data_only=solo_datos, read_only=solo_lectura)


def _leer_filas(ruta: Path, hoja: str | None = None) -> list[list]:
    """Devuelve las filas de un xlsx/csv/txt como listas de valores."""
    suf = ruta.suffix.lower()
    if suf in (".csv", ".txt"):
        filas: list[list] = []
        with ruta.open("r", encoding="utf-8-sig", newline="") as fh:
            muestra = fh.read(4096)
            fh.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t|")
            except csv.Error:
                dialecto = csv.excel
            for fila in csv.reader(fh, dialecto):
                filas.append(list(fila))
        return filas
    # read_only: el ReporteGlosasReclamPAQUETE trae decenas de miles de filas y
    # solo lo leemos (sin read_only tarda ~30 s en vez de ~3 s).
    wb = _abrir_libro(ruta, solo_lectura=True)
    try:
        hojas = [wb[hoja]] if hoja else list(wb.worksheets)
        filas = []
        for ws in hojas:
            filas.extend([list(f) for f in ws.iter_rows(values_only=True)])
        return filas
    finally:
        wb.close()


def _fila_encabezado(filas: list[list], alias: dict[str, tuple[str, ...]], minimo: int = 3) -> int:
    """Índice de la fila que sirve de encabezado (la que más alias reconoce)."""
    mejor, mejor_puntaje = -1, 0
    for i, fila in enumerate(filas[:30]):
        celdas = {_norm(c) for c in fila if c is not None}
        puntaje = sum(1 for opciones in alias.values() if celdas & set(opciones))
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = i, puntaje
    return mejor if mejor_puntaje >= minimo else -1


def _mapear_columnas(fila: list, alias: dict[str, tuple[str, ...]]) -> dict[str, int]:
    cols: dict[str, int] = {}
    for j, celda in enumerate(fila):
        etiqueta = _norm(celda)
        if not etiqueta:
            continue
        for campo, opciones in alias.items():
            if campo in cols:
                continue
            if etiqueta in opciones or any(etiqueta.startswith(o) for o in opciones):
                cols[campo] = j
                break
    return cols


# ─── 1) Consolidado de facturas ──────────────────────────────────────────────


def leer_consolidado(ruta: Path) -> tuple[list[str], list[str]]:
    """Facturas a trabajar, sin duplicados.

    Devuelve (facturas_unicas_en_orden, duplicadas). Busca primero una columna
    con encabezado de factura; si no la encuentra, rastrea cualquier celda con
    forma de factura HUS.
    """
    filas = _leer_filas(ruta)
    crudas: list[str] = []

    idx_hdr, col = -1, -1
    for i, fila in enumerate(filas[:30]):
        for j, celda in enumerate(fila):
            if _norm(celda) in _ALIAS_FACTURA_CONSOLIDADO:
                idx_hdr, col = i, j
                break
        if col >= 0:
            break

    if col >= 0:
        for fila in filas[idx_hdr + 1 :]:
            if col < len(fila):
                texto = str(fila[col] or "").strip()
                if texto:
                    crudas.append(texto)
    else:
        for fila in filas:
            for celda in fila:
                m = _RE_FACTURA.search(str(celda or ""))
                if m:
                    crudas.append(m.group(0))

    vistas: dict[str, str] = {}
    unicas: list[str] = []
    duplicadas: list[str] = []
    for cruda in crudas:
        clave = normalizar_factura(cruda)
        if clave in ("", "0"):
            continue
        if clave in vistas:
            duplicadas.append(cruda)
            continue
        vistas[clave] = cruda
        unicas.append(cruda)
    return unicas, duplicadas


# ─── 2) Reporte de glosas ────────────────────────────────────────────────────


def leer_reporte_glosas(ruta: Path, paquete: str | None = None) -> dict[str, list[FilaGlosa]]:
    """Agrupa las filas del ReporteGlosasReclamPAQUETE por factura normalizada."""
    filas = _leer_filas(ruta)
    idx = _fila_encabezado(filas, _ALIAS_COL_GLOSA, minimo=4)
    if idx < 0:
        raise SystemExit(
            f"No reconocí el encabezado del reporte de glosas en {ruta.name}. "
            "Se esperan columnas como 'Número Factura', 'Valor Aprobado' y 'Valor Glosado'."
        )
    cols = _mapear_columnas(filas[idx], _ALIAS_COL_GLOSA)
    faltan = [c for c in ("factura", "valor_glosado") if c not in cols]
    if faltan:
        raise SystemExit(f"Al reporte de glosas le faltan columnas: {', '.join(faltan)}")

    def val(fila: list, campo: str):
        j = cols.get(campo, -1)
        return fila[j] if 0 <= j < len(fila) else None

    por_factura: dict[str, list[FilaGlosa]] = {}
    for fila in filas[idx + 1 :]:
        factura = str(val(fila, "factura") or "").strip()
        if not factura:
            continue
        clave = normalizar_factura(factura)
        if clave in ("", "0"):
            continue
        if paquete and _norm(val(fila, "paquete")) != _norm(paquete):
            continue
        por_factura.setdefault(clave, []).append(
            FilaGlosa(
                factura=factura,
                codigo=str(val(fila, "codigo") or "").strip(),
                descripcion=str(val(fila, "descripcion") or "").strip(),
                tipo_elemento=str(val(fila, "tipo_elemento") or "").strip(),
                cant_reclamada=_parse_valor(val(fila, "cant_reclamada")),
                valor_reclamado=_parse_valor(val(fila, "valor_reclamado")),
                cant_aprobada=_parse_valor(val(fila, "cant_aprobada")),
                valor_aprobado=_parse_valor(val(fila, "valor_aprobado")),
                valor_glosado=_parse_valor(val(fila, "valor_glosado")),
                descripcion_glosa=str(val(fila, "descripcion_glosa") or "").strip(),
                anotacion=str(val(fila, "anotacion") or "").strip(),
            )
        )
    return por_factura


# ─── 3) Lectura de la hoja del detallado ─────────────────────────────────────


def _ancla_merge(ws, fila: int, col: int) -> tuple[int, int]:
    """Si la celda está combinada, devuelve la celda superior izquierda."""
    for rango in ws.merged_cells.ranges:
        if rango.min_row <= fila <= rango.max_row and rango.min_col <= col <= rango.max_col:
            return rango.min_row, rango.min_col
    return fila, col


def _leer(ws, fila: int, col: int):
    f, c = _ancla_merge(ws, fila, col)
    return ws.cell(row=f, column=c).value


def _escribir(ws, fila: int, col: int, valor) -> None:
    f, c = _ancla_merge(ws, fila, col)
    ws.cell(row=f, column=c).value = valor


def _buscar_fila(ws, marca: str, desde: int = 1, hasta: int | None = None) -> tuple[int, int]:
    """(fila, columna) de la primera celda cuyo texto empieza por `marca`."""
    marca_n = _norm(marca)
    hasta = hasta or ws.max_row
    for fila in ws.iter_rows(min_row=desde, max_row=hasta):
        for celda in fila:
            if celda.value is None:
                continue
            texto = _norm(celda.value)
            if texto.startswith(marca_n):
                return celda.row, celda.column
    return -1, -1


def _celdas_con_texto(ws, fila: int) -> list[tuple[int, str]]:
    out = []
    for celda in ws[fila]:
        if celda.value is None:
            continue
        texto = str(celda.value).strip()
        if texto:
            out.append((celda.column, texto))
    return out


def detectar_estructura(ws) -> dict:
    """Ubica el título, la tabla de ítems y el bloque de totales de la hoja."""
    fila_titulo, col_titulo = _buscar_fila(ws, TITULO_ORIGINAL)
    if fila_titulo < 0:
        fila_titulo, col_titulo = _buscar_fila(ws, TITULO_NUEVO)

    fila_hdr = -1
    cols: dict[str, int] = {}
    for fila in ws.iter_rows(min_row=max(fila_titulo, 1), max_row=ws.max_row):
        etiquetas = {_norm(c.value): c.column for c in fila if c.value is not None}
        if not etiquetas:
            continue
        cand = _mapear_columnas_ws(etiquetas)
        if {"nombre", "cantidad"} <= set(cand) and ("vr_ent" in cand or "vr_unit" in cand):
            fila_hdr, cols = fila[0].row, cand
            break

    fila_subtotal, _ = _buscar_fila(ws, MARCA_SUBTOTAL, desde=max(fila_hdr, 1))
    return {
        "fila_titulo": fila_titulo,
        "col_titulo": col_titulo,
        "fila_hdr": fila_hdr,
        "cols": cols,
        "fila_subtotal": fila_subtotal,
    }


def _mapear_columnas_ws(etiquetas: dict[str, int]) -> dict[str, int]:
    cols: dict[str, int] = {}
    for campo, opciones in _ALIAS_COL_ITEM.items():
        for etiqueta, col in etiquetas.items():
            if etiqueta in opciones or any(etiqueta.startswith(o) for o in opciones):
                cols.setdefault(campo, col)
                break
    return cols


def leer_bloques(ws, est: dict) -> list[Bloque]:
    """Recorre la tabla de ítems y la parte en grupos, ítems y continuaciones.

    - **Ítem**: la fila trae cantidad y valor.
    - **Título de grupo**: texto que arranca a la izquierda de la columna NOMBRE.
    - **Continuación**: texto en la columna NOMBRE (nombres largos que el
      sistema parte en dos renglones); pertenece al ítem de arriba.
    """
    fila_hdr, fila_fin = est["fila_hdr"], est["fila_subtotal"]
    cols = est["cols"]
    if fila_hdr < 0 or fila_fin < 0:
        return []

    col_nombre = cols.get("nombre", 2)
    bloques: list[Bloque] = [Bloque(titulo="", fila_titulo=None, fila_fin=fila_fin - 1)]

    for fila in range(fila_hdr + 1, fila_fin):
        contenido = _celdas_con_texto(ws, fila)
        cantidad = _parse_valor(_leer(ws, fila, cols["cantidad"])) if "cantidad" in cols else 0.0
        vr_unit = _parse_valor(_leer(ws, fila, cols["vr_unit"])) if "vr_unit" in cols else 0.0
        vr_ent = _parse_valor(_leer(ws, fila, cols["vr_ent"])) if "vr_ent" in cols else 0.0
        vr_pac = _parse_valor(_leer(ws, fila, cols["vr_pac"])) if "vr_pac" in cols else 0.0

        if cantidad > 0 and (vr_unit > 0 or vr_ent > 0):
            codigo = str(_leer(ws, fila, cols["codigo"]) or "").strip() if "codigo" in cols else ""
            if not codigo:
                # El sistema imprime el código indentado, no bajo el rótulo
                # 'CÓDIGO': lo tomamos del primer texto a la izquierda del nombre.
                izquierda = [t for c, t in contenido if c < col_nombre]
                codigo = izquierda[0] if izquierda else ""
            nombre = str(_leer(ws, fila, col_nombre) or "").strip()
            bloques[-1].items.append(
                ItemDetallado(
                    fila=fila,
                    filas=[fila],
                    grupo=bloques[-1].titulo,
                    codigo=codigo,
                    nombre=nombre,
                    cantidad=cantidad,
                    vr_unit=vr_unit,
                    vr_pac=vr_pac,
                    vr_ent=vr_ent or cantidad * vr_unit,
                )
            )
            continue

        if not contenido:
            continue

        col_ini = min(c for c, _ in contenido)
        if col_ini < col_nombre:
            # Título de grupo: cierra el bloque anterior y abre uno nuevo.
            bloques[-1].fila_fin = fila - 1
            titulo = " ".join(t for _, t in contenido)
            bloques.append(Bloque(titulo=titulo, fila_titulo=fila, fila_fin=fila_fin - 1))
        elif bloques[-1].items:
            # Continuación del nombre del ítem anterior.
            item = bloques[-1].items[-1]
            item.filas.append(fila)
            item.nombre = f"{item.nombre} {' '.join(t for _, t in contenido)}".strip()

    return [b for b in bloques if b.items or b.fila_titulo is not None]


# ─── 4) Cruce contra el reporte de glosas ────────────────────────────────────


def _indexar(glosas: list[FilaGlosa]) -> dict[str, dict[str, list[FilaGlosa]]]:
    idx: dict[str, dict[str, list[FilaGlosa]]] = {"codigo": {}, "descripcion": {}, "unitario": {}}
    for g in glosas:
        if g.codigo:
            idx["codigo"].setdefault(_norm_codigo(g.codigo), []).append(g)
        if g.descripcion:
            idx["descripcion"].setdefault(_norm_desc(g.descripcion), []).append(g)
        if g.vr_unit:
            idx["unitario"].setdefault(f"{round(g.vr_unit, 2):.2f}", []).append(g)
    return idx


def cruzar_item(
    item: ItemDetallado, idx: dict[str, dict[str, list[FilaGlosa]]]
) -> tuple[list[FilaGlosa], str]:
    """Filas del reporte que corresponden al ítem, y por qué criterio cruzaron.

    Se busca por código, luego por descripción y por último por valor unitario
    (los dispositivos médicos traen código INVIMA en el reporte y código interno
    en la factura, así que el código NO siempre cruza). Las filas se marcan como
    usadas para que dos ítems distintos no se lleven las mismas.
    """
    intentos = (
        ("codigo", _norm_codigo(item.codigo)),
        ("descripcion", _norm_desc(item.nombre)),
        ("unitario", f"{round(item.vr_unit, 2):.2f}" if item.vr_unit else ""),
    )
    for criterio, clave in intentos:
        if not clave:
            continue
        candidatas = [g for g in idx[criterio].get(clave, []) if not g.usada]
        if not candidatas:
            continue
        for g in candidatas:
            g.usada = True
        return candidatas, criterio
    return [], ""


def decidir(
    item: ItemDetallado, filas: list[FilaGlosa], modo_parcial: str, sin_cruce: str
) -> tuple[str, float, float, str]:
    """(accion, cantidad_nueva, vr_ent_nuevo, observacion)."""
    if not filas:
        if sin_cruce == "quitar":
            return "QUITADO", 0.0, 0.0, "No aparece en el reporte de glosas"
        return (
            "SIN_CRUCE",
            item.cantidad,
            item.vr_ent,
            ("No aparece en el reporte de glosas: se conserva, REVISAR a mano"),
        )

    glosado = sum(g.valor_glosado for g in filas)
    if glosado <= TOLERANCIA_PESOS:
        return "QUITADO", 0.0, 0.0, "La entidad ya lo aprobó (valor glosado 0)"

    if glosado >= item.vr_ent - TOLERANCIA_PESOS:
        return "CONSERVADO", item.cantidad, item.vr_ent, "Sigue glosado en su totalidad"

    # Aprobado a medias.
    if modo_parcial == "conservar":
        return (
            "CONSERVADO",
            item.cantidad,
            item.vr_ent,
            (
                f"Aprobado parcial (glosado ${glosado:,.0f}), se conserva completo por --modo-parcial"
            ),
        )
    if modo_parcial == "quitar":
        return (
            "QUITADO",
            0.0,
            0.0,
            (f"Aprobado parcial (glosado ${glosado:,.0f}), se quita por --modo-parcial"),
        )

    if item.vr_unit > 0:
        cantidad = round(glosado / item.vr_unit, 2)
    else:
        cantidad = sum(g.cant_reclamada - g.cant_aprobada for g in filas)
    cantidad = round(cantidad, 2)
    if cantidad == int(cantidad):
        cantidad = float(int(cantidad))
    nota = f"Aprobado parcial: de {item.cantidad:g} queda(n) {cantidad:g} sin pagar"
    if len(filas) > 1:
        nota += f" (sumadas {len(filas)} filas del reporte)"
    return "AJUSTADO", cantidad, glosado, nota


# ─── 5) Edición de la hoja ───────────────────────────────────────────────────


def eliminar_filas(ws, filas: set[int]) -> None:
    """Borra filas ajustando a mano lo que openpyxl NO ajusta: celdas
    combinadas, altos de fila e imágenes ancladas."""
    for fila in sorted(filas, reverse=True):
        ws.delete_rows(fila, 1)
        _ajustar_merges(ws, fila)
        _ajustar_altos(ws, fila)
        _ajustar_imagenes(ws, fila)


def _ajustar_merges(ws, borrada: int) -> None:
    from openpyxl.worksheet.cell_range import CellRange

    nuevos = []
    for rango in list(ws.merged_cells.ranges):
        min_r, max_r = rango.min_row, rango.max_row
        if min_r > borrada:
            min_r, max_r = min_r - 1, max_r - 1
        elif max_r >= borrada:
            max_r -= 1
        ws.merged_cells.ranges.remove(rango)
        if max_r >= min_r and not (min_r == max_r and rango.min_col == rango.max_col):
            nuevos.append(
                CellRange(
                    min_col=rango.min_col, min_row=min_r, max_col=rango.max_col, max_row=max_r
                )
            )
    for r in nuevos:
        ws.merged_cells.add(r)


def _ajustar_altos(ws, borrada: int) -> None:
    dims = dict(ws.row_dimensions.items())
    ws.row_dimensions.clear()
    for fila, dim in sorted(dims.items()):
        if fila == borrada:
            continue
        destino = fila - 1 if fila > borrada else fila
        dim.index = destino
        ws.row_dimensions[destino] = dim


def _ajustar_imagenes(ws, borrada: int) -> None:
    imagenes = getattr(ws, "_images", None)
    if not imagenes:
        return
    quedan = []
    for img in imagenes:
        ancla = getattr(img, "anchor", None)
        desde = getattr(ancla, "_from", None)
        if desde is None:
            quedan.append(img)
            continue
        if desde.row + 1 == borrada:  # el ancla es 0-based
            continue  # la imagen vivía en la fila borrada (logo, QR)
        if desde.row + 1 > borrada:
            desde.row -= 1
            hasta = getattr(ancla, "to", None)
            if hasta is not None:
                hasta.row -= 1
        quedan.append(img)
    ws._images = quedan


def _valor_totales(ws, fila: int, col_valor: int) -> tuple[int, int]:
    """Celda donde vive el importe de una fila de totales."""
    if col_valor:
        f, c = _ancla_merge(ws, fila, col_valor)
        if ws.cell(row=f, column=c).value is not None:
            return f, c
    ultima = (fila, col_valor or 1)
    for celda in ws[fila]:
        if celda.value is None:
            continue
        if isinstance(celda.value, (int, float)) or _parse_valor(celda.value):
            ultima = (celda.row, celda.column)
    return ultima


def recalcular_totales(ws, est: dict, subtotal: float) -> None:
    """Reescribe subtotal, total de la orden y el total en letras."""
    col_valor = est["cols"].get("vr_ent", 0)
    fila_sub = est["fila_subtotal"]
    if fila_sub > 0:
        f, c = _valor_totales(ws, fila_sub, col_valor)
        ws.cell(row=f, column=c).value = subtotal

    descuentos = 0.0
    for marca in (MARCA_COPAGO, MARCA_ANTICIPO, MARCA_COPAGO_USUARIO):
        fila, _ = _buscar_fila(ws, marca, desde=fila_sub if fila_sub > 0 else 1)
        if fila > 0:
            f, c = _valor_totales(ws, fila, col_valor)
            descuentos += _parse_valor(ws.cell(row=f, column=c).value)

    total = subtotal - descuentos
    fila_total, _ = _buscar_fila(ws, MARCA_TOTAL_ORDEN, desde=fila_sub if fila_sub > 0 else 1)
    if fila_total > 0:
        f, c = _valor_totales(ws, fila_total, col_valor)
        ws.cell(row=f, column=c).value = total

    fila_letras, col_letras = _buscar_fila(
        ws, MARCA_TOTAL_LETRAS, desde=fila_total if fila_total > 0 else 1
    )
    if fila_letras > 0:
        for col in range(col_letras + 1, (col_valor or ws.max_column) + 1):
            f, c = _ancla_merge(ws, fila_letras, col)
            if (f, c) != (fila_letras, col_letras):
                ws.cell(row=f, column=c).value = numero_a_letras(total)
                break


def procesar_hoja(
    ws,
    factura: str,
    glosas: list[FilaGlosa],
    *,
    modo_parcial: str = "ajustar",
    sin_cruce: str = "conservar",
    aplicar: bool = True,
) -> ResultadoHoja:
    """Limpia el encabezado, poda los ítems aprobados y recalcula los totales."""
    res = ResultadoHoja(hoja=ws.title, factura=factura, estado="AJUSTADA")
    est = detectar_estructura(ws)
    if est["fila_hdr"] < 0 or est["fila_subtotal"] < 0:
        res.estado = "SIN_ESTRUCTURA"
        res.observacion = (
            "No encontré la tabla de ítems (CÓDIGO/NOMBRE/CANT) o la fila "
            f"'{MARCA_SUBTOTAL}'. La hoja queda sin tocar."
        )
        return res

    bloques = leer_bloques(ws, est)
    items = [i for b in bloques for i in b.items]
    res.items_total = len(items)
    res.subtotal_antes = sum(i.vr_ent for i in items)

    idx = _indexar(glosas)
    a_borrar: set[int] = set()
    subtotal = 0.0

    for bloque in bloques:
        vivos = 0
        for item in bloque.items:
            filas, criterio = cruzar_item(item, idx)
            accion, cant, valor, nota = decidir(item, filas, modo_parcial, sin_cruce)
            det = ResultadoItem(
                factura=factura,
                hoja=ws.title,
                grupo=bloque.titulo,
                codigo=item.codigo,
                nombre=item.nombre,
                cant_orig=item.cantidad,
                vr_ent_orig=item.vr_ent,
                valor_reclamado=sum(g.valor_reclamado for g in filas),
                valor_aprobado=sum(g.valor_aprobado for g in filas),
                valor_glosado=sum(g.valor_glosado for g in filas),
                accion=accion,
                cant_nueva=cant,
                vr_ent_nuevo=valor,
                cruce=criterio,
                filas_reporte=len(filas),
                observacion=nota,
            )
            res.detalle.append(det)

            if accion == "QUITADO":
                res.items_quitados += 1
                a_borrar.update(item.filas)
                continue

            vivos += 1
            subtotal += valor
            if accion == "AJUSTADO":
                res.items_ajustados += 1
                if aplicar:
                    _escribir(ws, item.fila, est["cols"]["cantidad"], cant)
                    if "vr_ent" in est["cols"]:
                        _escribir(ws, item.fila, est["cols"]["vr_ent"], valor)
            elif accion == "SIN_CRUCE":
                res.items_sin_cruce += 1
            else:
                res.items_conservados += 1

        # Grupo que se quedó sin ítems: se borra el bloque completo (título,
        # renglones en blanco y todo), igual que se hace a mano.
        if bloque.fila_titulo is not None and bloque.items and vivos == 0:
            a_borrar.update(range(bloque.fila_titulo, bloque.fila_fin + 1))

    res.subtotal_despues = subtotal

    if not aplicar:
        return res

    # Título y encabezado institucional.
    fila_titulo = est["fila_titulo"]
    if fila_titulo > 0:
        celda = ws.cell(row=fila_titulo, column=est["col_titulo"])
        texto = str(celda.value or "")
        celda.value = re.sub(re.escape(TITULO_ORIGINAL), TITULO_NUEVO, texto, flags=re.IGNORECASE)
        a_borrar.update(range(1, fila_titulo))
    else:
        res.observacion = (
            f"No encontré el título '{TITULO_ORIGINAL}': no se quitó el encabezado "
            "institucional ni se renombró el título."
        )

    eliminar_filas(ws, a_borrar)

    est2 = detectar_estructura(ws)
    recalcular_totales(ws, est2 if est2["fila_subtotal"] > 0 else est, subtotal)
    return res


# ─── Orquestación ────────────────────────────────────────────────────────────


def factura_de_hoja(ws, est: dict | None = None) -> str:
    """Número de factura de la hoja: al lado del título, en cualquier celda o
    en el nombre de la hoja."""
    est = est or detectar_estructura(ws)
    fila = est.get("fila_titulo", -1)
    if fila > 0:
        for celda in ws[fila]:
            m = _RE_FACTURA.search(str(celda.value or ""))
            if m:
                return m.group(0).replace(" ", "")
    for f in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 40)):
        for celda in f:
            m = _RE_FACTURA.search(str(celda.value or ""))
            if m:
                return m.group(0).replace(" ", "")
    m = _RE_FACTURA.search(ws.title)
    return m.group(0).replace(" ", "") if m else ws.title


def procesar_libro(
    ruta_detallado: Path,
    facturas: list[str],
    glosas_por_factura: dict[str, list[FilaGlosa]],
    *,
    modo_parcial: str = "ajustar",
    sin_cruce: str = "conservar",
    aplicar: bool = True,
    salida: Path | None = None,
) -> list[ResultadoHoja]:
    wb = _abrir_libro(ruta_detallado)
    quiero = {normalizar_factura(f) for f in facturas}
    resultados: list[ResultadoHoja] = []

    for ws in list(wb.worksheets):
        factura = factura_de_hoja(ws)
        clave = normalizar_factura(factura)
        if quiero and clave not in quiero:
            resultados.append(
                ResultadoHoja(
                    hoja=ws.title,
                    factura=factura,
                    estado="ELIMINADA",
                    observacion="No está en el consolidado de facturas a trabajar",
                )
            )
            if aplicar:
                wb.remove(ws)
            continue

        glosas = glosas_por_factura.get(clave, [])
        if not glosas:
            resultados.append(
                ResultadoHoja(
                    hoja=ws.title,
                    factura=factura,
                    estado="SIN_GLOSAS",
                    observacion=(
                        "No tiene filas en el reporte de glosas: la hoja queda "
                        "tal cual. REVISAR (¿otro paquete?)"
                    ),
                )
            )
            continue

        resultados.append(
            procesar_hoja(
                ws,
                factura,
                [FilaGlosa(**{**g.__dict__, "usada": False}) for g in glosas],
                modo_parcial=modo_parcial,
                sin_cruce=sin_cruce,
                aplicar=aplicar,
            )
        )

    if aplicar and salida is not None:
        if not wb.worksheets:
            logger.warning(
                "%s: ninguna hoja quedó en pie, no se escribe salida", ruta_detallado.name
            )
        else:
            salida.parent.mkdir(parents=True, exist_ok=True)
            wb.save(salida)
    wb.close()
    return resultados


CAMPOS_CSV = [
    "FACTURA",
    "HOJA",
    "GRUPO",
    "CODIGO",
    "NOMBRE",
    "CANT_ORIGINAL",
    "VR_ENT_ORIGINAL",
    "VALOR_RECLAMADO",
    "VALOR_APROBADO",
    "VALOR_GLOSADO",
    "ACCION",
    "CANT_NUEVA",
    "VR_ENT_NUEVO",
    "CRUCE_POR",
    "FILAS_REPORTE",
    "OBSERVACION",
]


def escribir_bitacora(ruta: Path, resultados: list[ResultadoHoja]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(CAMPOS_CSV)
        for hoja in resultados:
            if not hoja.detalle:
                w.writerow(
                    [
                        hoja.factura,
                        hoja.hoja,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        hoja.estado,
                        "",
                        "",
                        "",
                        "",
                        hoja.observacion,
                    ]
                )
                continue
            for d in hoja.detalle:
                w.writerow(
                    [
                        d.factura,
                        d.hoja,
                        d.grupo,
                        d.codigo,
                        d.nombre,
                        f"{d.cant_orig:g}",
                        f"{d.vr_ent_orig:.0f}",
                        f"{d.valor_reclamado:.0f}",
                        f"{d.valor_aprobado:.0f}",
                        f"{d.valor_glosado:.0f}",
                        d.accion,
                        f"{d.cant_nueva:g}",
                        f"{d.vr_ent_nuevo:.0f}",
                        d.cruce,
                        d.filas_reporte,
                        d.observacion,
                    ]
                )


def _resumir(resultados: list[ResultadoHoja]) -> None:
    ajustadas = [r for r in resultados if r.estado == "AJUSTADA"]
    eliminadas = [r for r in resultados if r.estado == "ELIMINADA"]
    sin_glosas = [r for r in resultados if r.estado == "SIN_GLOSAS"]
    sin_estruct = [r for r in resultados if r.estado == "SIN_ESTRUCTURA"]

    logger.info("─" * 68)
    logger.info("Hojas ajustadas .......... %d", len(ajustadas))
    logger.info("Hojas eliminadas ......... %d (no estaban en el consolidado)", len(eliminadas))
    if sin_glosas:
        logger.warning(
            "Hojas sin glosas ......... %d  → %s",
            len(sin_glosas),
            ", ".join(r.factura for r in sin_glosas[:10]),
        )
    if sin_estruct:
        logger.warning(
            "Hojas sin estructura ..... %d  → %s",
            len(sin_estruct),
            ", ".join(r.factura for r in sin_estruct[:10]),
        )
    if not ajustadas:
        return
    logger.info(
        "Ítems: %d quitados, %d ajustados, %d conservados, %d sin cruce",
        sum(r.items_quitados for r in ajustadas),
        sum(r.items_ajustados for r in ajustadas),
        sum(r.items_conservados for r in ajustadas),
        sum(r.items_sin_cruce for r in ajustadas),
    )
    logger.info(
        "Valor: antes $%s → sigue glosado $%s",
        f"{sum(r.subtotal_antes for r in ajustadas):,.0f}",
        f"{sum(r.subtotal_despues for r in ajustadas):,.0f}",
    )
    revisar = [d for r in ajustadas for d in r.detalle if d.accion == "SIN_CRUCE"]
    if revisar:
        logger.warning(
            "REVISAR: %d ítem(s) no cruzaron con el reporte de glosas "
            "(quedaron en la factura). Ver la bitácora CSV.",
            len(revisar),
        )


def _diagnosticar(resultados: list[ResultadoHoja]) -> None:
    for r in resultados:
        if r.estado == "ELIMINADA":
            logger.info("%-14s hoja '%s' → SE ELIMINA (%s)", r.factura, r.hoja, r.observacion)
            continue
        logger.info(
            "%-14s hoja '%s' → %s | ítems %d (quitar %d, ajustar %d, dejar %d, revisar %d)"
            " | $%s → $%s",
            r.factura,
            r.hoja,
            r.estado,
            r.items_total,
            r.items_quitados,
            r.items_ajustados,
            r.items_conservados,
            r.items_sin_cruce,
            f"{r.subtotal_antes:,.0f}",
            f"{r.subtotal_despues:,.0f}",
        )
        if r.observacion:
            logger.info("               %s", r.observacion)
        for d in r.detalle:
            logger.info(
                "               [%-10s] %-12s %-42s %g → %g  ($%s → $%s) %s",
                d.accion,
                d.codigo,
                d.nombre[:42],
                d.cant_orig,
                d.cant_nueva,
                f"{d.vr_ent_orig:,.0f}",
                f"{d.vr_ent_nuevo:,.0f}",
                f"[{d.cruce}]" if d.cruce else "[sin cruce]",
            )


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Deja el detallado de factura solo con lo que sigue glosado.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--consolidado",
        type=Path,
        help="Excel/CSV con las facturas a trabajar (se le quitan los duplicados). "
        "Si se omite, se trabajan TODAS las hojas del detallado.",
    )
    p.add_argument(
        "--detallado",
        type=Path,
        nargs="+",
        required=True,
        help="Excel del detallado (una hoja por factura). Admite varios archivos.",
    )
    p.add_argument(
        "--reporte-glosas", type=Path, required=True, help="ReporteGlosasReclamPAQUETE NNNNN.xlsx"
    )
    p.add_argument(
        "--salida", type=Path, help="Excel corregido (o carpeta, si se pasan varios --detallado)."
    )
    p.add_argument("--reporte-csv", type=Path, help="Bitácora CSV ítem por ítem.")
    p.add_argument("--paquete", help="Filtrar el reporte de glosas por número de paquete.")
    p.add_argument(
        "--modo-parcial",
        choices=("ajustar", "conservar", "quitar"),
        default="ajustar",
        help="Qué hacer con los ítems que la entidad aprobó a medias. "
        "ajustar (por defecto): deja solo la parte que sigue glosada.",
    )
    p.add_argument(
        "--sin-cruce",
        choices=("conservar", "quitar"),
        default="conservar",
        help="Qué hacer con los ítems de la factura que NO aparecen en el reporte "
        "de glosas. Por defecto se conservan y se marcan para revisión.",
    )
    p.add_argument(
        "--diagnostico",
        action="store_true",
        help="Solo analiza y muestra qué haría; no escribe el Excel de salida.",
    )
    p.add_argument("--verbose", action="store_true", help="Log detallado.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    if not args.diagnostico and not args.salida:
        logger.error("Falta --salida (o usá --diagnostico para solo ver qué haría).")
        return 2

    facturas: list[str] = []
    if args.consolidado:
        if not args.consolidado.exists():
            logger.error("No existe el consolidado: %s", args.consolidado)
            return 2
        facturas, duplicadas = leer_consolidado(args.consolidado)
        logger.info(
            "Consolidado: %d factura(s) únicas, %d duplicada(s) descartada(s)",
            len(facturas),
            len(duplicadas),
        )
        if duplicadas:
            logger.info("Duplicadas: %s", ", ".join(duplicadas[:20]))
        if not facturas:
            logger.error("El consolidado no trajo ninguna factura reconocible.")
            return 2
    else:
        logger.warning("Sin --consolidado: se trabajan TODAS las hojas del detallado.")

    if not args.reporte_glosas.exists():
        logger.error("No existe el reporte de glosas: %s", args.reporte_glosas)
        return 2
    glosas = leer_reporte_glosas(args.reporte_glosas, paquete=args.paquete)
    logger.info(
        "Reporte de glosas: %d factura(s), %d fila(s)",
        len(glosas),
        sum(len(v) for v in glosas.values()),
    )

    if facturas:
        faltan = [f for f in facturas if normalizar_factura(f) not in glosas]
        if faltan:
            logger.warning(
                "%d factura(s) del consolidado no están en el reporte de glosas: %s",
                len(faltan),
                ", ".join(faltan[:20]),
            )

    varios = len(args.detallado) > 1
    resultados: list[ResultadoHoja] = []
    for ruta in args.detallado:
        if not ruta.exists():
            logger.error("No existe el detallado: %s", ruta)
            return 2
        salida = None
        if args.salida and not args.diagnostico:
            salida = (args.salida / f"{ruta.stem}_AJUSTADO.xlsx") if varios else args.salida
        logger.info("Procesando %s …", ruta.name)
        resultados.extend(
            procesar_libro(
                ruta,
                facturas,
                glosas,
                modo_parcial=args.modo_parcial,
                sin_cruce=args.sin_cruce,
                aplicar=not args.diagnostico,
                salida=salida,
            )
        )
        if salida:
            logger.info("Escrito: %s", salida)

    if args.diagnostico:
        _diagnosticar(resultados)
    _resumir(resultados)

    if args.reporte_csv:
        escribir_bitacora(args.reporte_csv, resultados)
        logger.info("Bitácora: %s", args.reporte_csv)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
