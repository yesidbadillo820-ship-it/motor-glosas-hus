"""organizar_objeciones_dispensario.py — PDF de auditoría del Dispensario → Excel OBJECIONES (DGH).

Lee uno o varios PDF "DETALLE DE AUDITORIA Y GLOSAS" que envía el auditor del
Dispensario Médico Bucaramanga (CONSORCIO AUDITOOL) y produce, por cada
factura glosada, un Excel con UNA FILA POR OBJECIÓN en el formato OBJECIONES
que se importa en Dinámica Gerencial (mismo layout del ejemplo
OBJECIONES_EMSSANAR_HUS<n>.xlsx: columnas CDCONSEC..CROTIPOBJ).

El PDF es una tabla multicolumna (PREFIJO | FACTURA | FECHA ATENCION |
NOMBRES | VALOR FACTURA | VALOR OBJETADO | CODIGO+CONCEPTO | MOTIVO). Las
columnas CONCEPTO y MOTIVO vienen pegadas en el texto plano, así que la
extracción se hace por coordenadas de carácter (pdfplumber) y no por regex
sobre el texto corrido.

Validación integrada: la suma de los valores objetados extraídos de cada
factura se compara contra el "Total Factura" que imprime el propio PDF; si no
cuadra, el script lo marca y termina con código de salida 1.

DOS FUENTES DE ENTRADA
----------------------
1. **PDF** del auditor (``--pdf`` / ``--carpeta``): lo original de este bot.
2. **Excel** de glosa inicial (``--entrada-excel``), que es como llega ahora el
   listado: FACTURA | VALOR GLOSA INICIAL | SERVICIO OBJETADO | CODIGO GLOSA
   INICIAL | DESCRIPCION GLOSA INICIAL. Ese archivo trae el **nombre** del
   servicio pero no su código, así que con ``--servicios-dgh`` (el export de
   servicios facturados) se busca de qué renglón del DGH habla cada objeción y
   SLNSERPRO queda con el código que Dinámica Gerencial reconoce. El motor del
   cruce es el compartido: ``tools/_cruce_dgh.py``.

Reglas del formato que valen para las dos fuentes: **CTNCENCOS siempre vacía**
y **CROTIPOBJ por factura** (0 = ADMINISTRATIVA, 1 = MEDICA, 2 = MIXTA).

USO RÁPIDO
----------

    REM Excel de glosa inicial + export del DGH (lo de ahora)
    py tools\\organizar_objeciones_dispensario.py ^
        --entrada-excel "D:\\...\\dispensario_3_septiembre.xlsx" ^
        --servicios-dgh "D:\\...\\SERVICIOS_FACTURADOS_DGH.xlsx" ^
        --consolidado   "D:\\...\\OBJECIONES_DISPENSARIO_03092026.xlsx" ^
        --reporte-cruce "D:\\...\\CRUCE_DISPENSARIO_03-09-2026.xlsx" ^
        --fecha 03/09/2026

    # Un PDF (genera un Excel por factura glosada, en la carpeta del PDF)
    py tools\\organizar_objeciones_dispensario.py --pdf "D:\\...\\AUDITORIA_GLOSA_...pdf"

    # Carpeta con varios PDFs + salida en otra carpeta
    py tools\\organizar_objeciones_dispensario.py ^
        --carpeta "D:\\...\\GLOSAS_2026\\DISPENSARIO_<fecha>" ^
        --salida-dir "D:\\...\\GLOSAS_2026\\DISPENSARIO_<fecha>\\OBJECIONES"

    # Todo consolidado en un solo Excel
    py tools\\organizar_objeciones_dispensario.py --pdf <pdf> --consolidado objeciones.xlsx

DEPENDENCIAS
------------
    py -m pip install pdfplumber openpyxl
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# El motor del cruce contra el DGH es común a los bots (ver tools/_cruce_dgh.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cruce_dgh import (  # noqa: E402
    escribir_reporte_cruce,
    factura_larga,
    leer_servicios_dgh,
    resolver_servicio,
    traza,
    verificar_reglas,
)

logger = logging.getLogger("organizar_objeciones")

# ---------------------------------------------------------------------------
# Layout del PDF (coordenadas X de cada columna, página de 1029 pt de ancho).
# Un carácter pertenece a la columna donde cae el centro de su caja.
# ---------------------------------------------------------------------------
COLUMNAS = {
    "prefijo": (28.0, 68.0),
    "factura": (68.0, 113.0),
    "fecha": (113.0, 162.0),
    "nombre": (162.0, 330.0),
    "vfactura": (330.0, 382.0),
    "vobjetado": (382.0, 440.0),
    "concepto": (440.0, 659.5),
    "motivo": (659.5, 10_000.0),
}

# Banda vertical con datos (excluye cabecera de la tabla y pie de página).
Y_DATOS_MIN = 165.0
Y_DATOS_MAX = 592.0

# Código de glosa al inicio de la columna CONCEPTO: "CL03 01", "SO08 01", ...
RE_CODIGO_GLOSA = re.compile(r"^([A-Z]{2}\d{2})\s+(\d{2})\b\s*(.*)$", re.DOTALL)

# La misma, pero sin mirar mayúsculas: el Excel de glosa inicial a veces trae
# el código en minúscula ('ta01 01 TARIFAS-…'). El PDF sigue usando la de
# arriba, que es estricta a propósito.
RE_CODIGO_GLOSA_TEXTO = re.compile(r"^([A-Za-z]{2}\d{2})\s+(\d{2})\b\s*(.*)$", re.DOTALL)

# Prefijo de factura en la primera columna: "HUS" (2 a 5 letras).
RE_PREFIJO = re.compile(r"^[A-ZÑ]{2,5}$")

RE_FECHA = re.compile(r"\d{2}/\d{2}/\d{4}")
RE_VALOR = re.compile(r"[\d.]+,\d{2}")
RE_FECHA_IMPRESION = re.compile(r"Fecha\s+Impresi[oó]n:\s*(\d{2}/\d{2}/\d{2,4})")

# Servicio glosado dentro del motivo: "SE GLOSA CODIGO 21519H ..." o
# "SE GLOSA EL CODIGO 908337H ...".
RE_SERVICIO = re.compile(r"SE\s+GLOSA\s+(?:EL\s+)?CODIGO\s+([A-Z0-9]+)", re.IGNORECASE)

# Artefactos de extracción tipo "(cid:9)" (tabs embebidos en la fuente).
RE_CID = re.compile(r"\(cid:\d+\)")

ENCABEZADOS = [
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

FMT_CONTABLE = '_-* #,##0_-;\\-* #,##0_-;_-* "-"_-;_-@_-'
FMT_FECHA = "mm-dd-yy"


@dataclass
class Glosa:
    codigo: str  # CL0301, SO0801, ...
    concepto: str  # texto de la columna CONCEPTO DE GLOSA
    motivo: str  # texto de la columna MOTIVO DE GLOSA
    valor: int  # valor objetado en pesos


@dataclass
class Factura:
    prefijo: str
    numero: str
    fecha_atencion: str = ""
    paciente: str = ""
    valor_factura: int = 0
    total_objetado_pdf: int | None = None  # "Total Factura" del propio PDF
    glosas: list[Glosa] = field(default_factory=list)

    @property
    def cxc(self) -> str:
        """N° de CxC en DGH: prefijo + número a 10 dígitos (HUS0000530265)."""
        return f"{self.prefijo}{int(self.numero):010d}"

    @property
    def total_extraido(self) -> int:
        return sum(g.valor for g in self.glosas)


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _to_int(s: str) -> int:
    """'4.677.656,00' (formato Colombia) → 4677656. La parte decimal se ignora."""
    parte_entera = s.split(",")[0]
    return int(re.sub(r"\.", "", parte_entera) or "0")


def _limpiar(texto: str) -> str:
    """Colapsa espacios y remueve artefactos (cid:N) de la extracción."""
    return re.sub(r"\s+", " ", RE_CID.sub(" ", texto)).strip()


# ---------------------------------------------------------------------------
# Extracción por coordenadas
# ---------------------------------------------------------------------------


def _filas_de_pagina(page) -> list[dict[str, str]]:
    """Convierte una página en filas visuales: dict columna → texto.

    Agrupa los caracteres en renglones por su coordenada `top` (clusters con
    tolerancia, porque celdas de la misma fila pueden variar 1-2 pt) y dentro
    de cada renglón reparte los caracteres a su columna por el centro X.
    """
    chars = [c for c in page.chars if Y_DATOS_MIN <= c["top"] <= Y_DATOS_MAX]
    if not chars:
        return []

    chars.sort(key=lambda c: c["top"])
    renglones: list[list[dict]] = [[chars[0]]]
    for c in chars[1:]:
        if c["top"] - renglones[-1][-1]["top"] <= 3.0:
            renglones[-1].append(c)
        else:
            renglones.append([c])

    filas: list[dict[str, str]] = []
    for renglon in renglones:
        fila: dict[str, str] = {}
        for nombre, (x0, x1) in COLUMNAS.items():
            celda = [c for c in renglon if x0 <= (c["x0"] + c["x1"]) / 2 < x1]
            celda.sort(key=lambda c: c["x0"])
            texto, x_prev = "", None
            for c in celda:
                if x_prev is not None and c["x0"] - x_prev > 1.2:
                    texto += " "
                texto += c["text"]
                x_prev = c["x1"]
            fila[nombre] = _limpiar(texto)
        if any(fila.values()):
            filas.append(fila)
    return filas


def parsear_pdf(ruta: Path) -> tuple[list[Factura], str]:
    """Extrae las facturas con sus glosas de un PDF DETALLE DE AUDITORIA Y GLOSAS.

    Devuelve (facturas, fecha_impresion "dd/mm/yy").
    """
    try:
        import pdfplumber
    except ImportError:
        sys.stderr.write("ERROR: falta pdfplumber.\nInstalalo con:  py -m pip install pdfplumber\n")
        sys.exit(2)

    facturas: list[Factura] = []
    factura: Factura | None = None
    glosa: Glosa | None = None
    fecha_impresion = ""

    with pdfplumber.open(str(ruta)) as pdf:
        for page in pdf.pages:
            texto_pagina = page.extract_text() or ""
            m_imp = RE_FECHA_IMPRESION.search(texto_pagina)
            if m_imp and not fecha_impresion:
                fecha_impresion = m_imp.group(1)

            for fila in _filas_de_pagina(page):
                # --- Cierre de factura: "Total Factura: HUS - <n>  <objetado> ... <a pagar>"
                if "Total" in fila["prefijo"]:
                    if factura is not None:
                        m_val = RE_VALOR.search(fila["vobjetado"])
                        if m_val:
                            factura.total_objetado_pdf = _to_int(m_val.group(0))
                        factura, glosa = None, None
                    continue

                # --- Encabezado de factura: prefijo (HUS) + número
                if RE_PREFIJO.match(fila["prefijo"]) and fila["factura"].replace(" ", "").isdigit():
                    glosa = None
                    factura = Factura(
                        prefijo=fila["prefijo"].strip(),
                        numero=fila["factura"].replace(" ", ""),
                        paciente=fila["nombre"],
                    )
                    m_fec = RE_FECHA.search(fila["fecha"])
                    if m_fec:
                        factura.fecha_atencion = m_fec.group(0)
                    m_vf = RE_VALOR.search(fila["vfactura"])
                    if m_vf:
                        factura.valor_factura = _to_int(m_vf.group(0))
                    facturas.append(factura)
                    # ojo: la primera glosa viene en el MISMO renglón (cae al código de abajo)

                if factura is None:
                    continue

                # --- Inicio de glosa: código "XX99 99" al comienzo de CONCEPTO
                m_cod = RE_CODIGO_GLOSA.match(fila["concepto"])
                if m_cod:
                    m_val = RE_VALOR.search(fila["vobjetado"])
                    glosa = Glosa(
                        codigo=m_cod.group(1) + m_cod.group(2),
                        concepto=m_cod.group(3).strip(),
                        motivo=fila["motivo"],
                        valor=_to_int(m_val.group(0)) if m_val else 0,
                    )
                    factura.glosas.append(glosa)
                    continue

                # --- Continuación de la glosa en curso
                if glosa is not None:
                    if fila["concepto"]:
                        glosa.concepto = _limpiar(glosa.concepto + " " + fila["concepto"])
                    if fila["motivo"]:
                        glosa.motivo = _limpiar(glosa.motivo + " " + fila["motivo"])

    return facturas, fecha_impresion


# ---------------------------------------------------------------------------
# Fuente 2: Excel de glosa inicial (FACTURA | VALOR | SERVICIO | CODIGO | DESC)
# ---------------------------------------------------------------------------


def _norm_header(h: object) -> str:
    """Encabezado en MAYÚSCULAS, sin tildes y sin espacios de más."""
    t = unicodedata.normalize("NFKD", str(h or "").strip().upper())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


ALIAS_EXCEL = {
    "factura": {"FACTURA", "NRO FACTURA", "NUMERO FACTURA", "NRO_FACTURA"},
    "valor": {"VALOR GLOSA INICIAL", "VALOR GLOSA", "VALOR OBJETADO", "VALOR"},
    "servicio": {"SERVICIO OBJETADO", "SERVICIO", "DESCRIPCION SERVICIO"},
    "codigo": {"CODIGO GLOSA INICIAL", "CODIGO GLOSA", "CODIGO DE GLOSA", "CODIGO"},
    "motivo": {
        "DESCRIPCION GLOSA INICIAL",
        "DESCRIPCION GLOSA",
        "MOTIVO",
        "MOTIVO DE GLOSA",
        "OBSERVACION",
    },
}

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


def codigo_y_concepto(texto: str) -> tuple[str, str]:
    """'TA08 01 TARIFAS-APOYO DIAGNÓSTICO - …' → ('TA0801', 'TARIFAS-APOYO …').

    El Excel del Dispensario pega el código (con un espacio en la mitad) y el
    texto del concepto en una sola columna.

    Algunos lotes traen el código en MINÚSCULA ('ta01 01 TARIFAS-…'). Se lee
    igual y sale en mayúscula, que es como lo recibe el DGH: en el lote del 7
    de septiembre esto dejaba 19 objeciones con CRNCONOBJ vacío y, de paso,
    una factura marcada como administrativa cuando era mixta (el `cl03 02`
    tampoco se leía).
    """
    t = _limpiar(texto)
    m = RE_CODIGO_GLOSA_TEXTO.match(t)
    if m:
        return (m.group(1) + m.group(2)).upper(), _limpiar(m.group(3))
    # Sin el espacio: 'TA0801 TARIFAS-…'
    m2 = re.match(r"^([A-Za-z]{2}\d{4})\b\s*(.*)$", t, re.DOTALL)
    if m2:
        return m2.group(1).upper(), _limpiar(m2.group(2))
    return "", t


def leer_excel_glosa_inicial(ruta: Path) -> list[dict]:
    """Lee el Excel de glosa inicial y devuelve una lista de objeciones."""
    from openpyxl import load_workbook

    wb = load_workbook(filename=str(ruta), data_only=True, read_only=True)
    try:
        ws = wb.active
        filas = ws.iter_rows(values_only=True)
        headers = list(next(filas, ()) or ())
        norm = [_norm_header(h) for h in headers]
        idx: dict[str, int] = {}
        for clave, alias in ALIAS_EXCEL.items():
            i = next((n for n, h in enumerate(norm) if h in alias), None)
            if i is not None:
                idx[clave] = i
        faltan = [c for c in ("factura", "valor", "codigo") if c not in idx]
        if faltan:
            raise ValueError(
                f"{ruta.name}: no encontré la(s) columna(s) {faltan}. "
                f"Encabezados leídos: {[h for h in headers if h]}"
            )

        def dato(fila, clave):
            i = idx.get(clave)
            return fila[i] if i is not None and i < len(fila) else None

        objeciones: list[dict] = []
        for n, fila in enumerate(filas, start=2):
            if fila is None:
                continue
            factura = str(dato(fila, "factura") or "").strip()
            if not factura:
                continue
            codigo, concepto = codigo_y_concepto(str(dato(fila, "codigo") or ""))
            objeciones.append(
                {
                    "fila_excel": n,
                    "cxc": factura_larga(factura),
                    "codigo": codigo,
                    "concepto": concepto,
                    "servicio": _limpiar(str(dato(fila, "servicio") or "")),
                    "motivo": _limpiar(str(dato(fila, "motivo") or "")),
                    "valor": _to_int(str(dato(fila, "valor") or "0")),
                }
            )
        return objeciones
    finally:
        wb.close()


def filas_desde_excel(
    objeciones: list[dict],
    fecha_doc: datetime,
    servicios_dgh: dict | None = None,
    trazas: list[dict] | None = None,
) -> list[list]:
    """Filas del formato OBJECIONES (16 columnas) desde el Excel de glosa
    inicial. Con `servicios_dgh`, SLNSERPRO queda con el código real del
    hospital; sin cruce confiable se deja vacío y el renglón se reporta."""
    consec: dict[str, int] = {}
    grupos: dict[str, set[str]] = defaultdict(set)
    for o in objeciones:
        grupos[o["cxc"]].add((o["codigo"] or "")[:2].upper())

    filas: list[list] = []
    for o in objeciones:
        if o["cxc"] not in consec:
            consec[o["cxc"]] = len(consec) + 1
        slnserpro = ""
        cruce = None
        if servicios_dgh is not None:
            cruce = resolver_servicio(
                servicios_dgh.get(o["cxc"], []),
                descripcion=o["servicio"],
                valor=o["valor"],
            )
            if cruce.linea is not None:
                slnserpro = cruce.linea.codigo
            if trazas is not None:
                trazas.append(
                    traza(
                        factura=o["cxc"],
                        codigo_objecion=o["codigo"],
                        valor=o["valor"],
                        cod_entidad="",
                        desc_entidad=o["servicio"],
                        unitario_entidad=0,
                        observacion=o["motivo"],
                        cruce=cruce,
                    )
                )
        observacion = f"{o['codigo']} {o['concepto']}: {o['motivo']}${o['valor']}"
        filas.append(
            [
                str(consec[o["cxc"]]),  # CDCONSEC
                fecha_doc,  # CDFECDOC
                o["cxc"],  # CRNCXC
                fecha_doc,  # CROFECOBJ
                None,  # CROREFERE
                None,  # CROOBSERV
                0,  # CROCLAOBJ
                None,  # CRNCLAOBJ
                "999",  # GENUSUARIO4
                o["codigo"] or None,  # CRNCONOBJ
                slnserpro or None,  # SLNSERPRO
                None,  # IDRIPS
                None,  # CTNCENCOS — siempre vacía (regla del área)
                o["valor"],  # CROVALOBJ
                observacion,  # CRDOBSERV
                crotipobj_factura(grupos[o["cxc"]]),  # CROTIPOBJ
            ]
        )
    return filas


# ---------------------------------------------------------------------------
# Armado del Excel OBJECIONES
# ---------------------------------------------------------------------------


def _servicio_de(glosa: Glosa) -> str:
    """Código del servicio/producto glosado, si el motivo lo menciona."""
    m = RE_SERVICIO.search(glosa.motivo)
    return m.group(1) if m else ""


def filas_objeciones(factura: Factura, fecha_doc: datetime) -> list[list]:
    """Filas (16 columnas) del formato OBJECIONES para una factura."""
    filas = []
    for g in factura.glosas:
        observacion = f"{g.codigo} {g.concepto}: {g.motivo}${g.valor}"
        filas.append(
            [
                "1",  # CDCONSEC
                fecha_doc,  # CDFECDOC
                factura.cxc,  # CRNCXC
                fecha_doc,  # CROFECOBJ
                None,  # CROREFERE
                None,  # CROOBSERV
                0,  # CROCLAOBJ
                None,  # CRNCLAOBJ
                "999",  # GENUSUARIO4
                g.codigo,  # CRNCONOBJ
                _servicio_de(g) or None,  # SLNSERPRO
                None,  # IDRIPS
                None,  # CTNCENCOS
                g.valor,  # CROVALOBJ
                observacion,  # CRDOBSERV
                0,  # CROTIPOBJ
            ]
        )
    return filas


def escribir_excel(filas: list[list], salida: Path) -> None:
    """Escribe el Excel con los mismos tipos y formatos del ejemplo de EMSSANAR."""
    try:
        from openpyxl import Workbook
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl. Instalalo con: py -m pip install openpyxl\n")
        sys.exit(2)

    formatos = {2: FMT_FECHA, 4: FMT_FECHA, 7: "General", 14: FMT_CONTABLE, 16: "0"}
    wb = Workbook()
    ws = wb.active
    ws.title = "OBJECIONES"
    ws.append(ENCABEZADOS)
    for fila in filas:
        ws.append(fila)
        r = ws.max_row
        for col in range(1, 17):
            ws.cell(row=r, column=col).number_format = formatos.get(col, "@")
    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(salida))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_fecha(s: str) -> datetime:
    """'10/07/26' o '10/07/2026' → datetime."""
    dd, mm, yy = s.split("/")
    anio = int(yy) + 2000 if len(yy) == 2 else int(yy)
    return datetime(anio, int(mm), int(dd))


def procesar(
    pdfs: list[Path],
    salida_dir: Path,
    entidad: str,
    fecha_cli: str | None,
    consolidado: Path | None,
) -> int:
    """Corre el pipeline completo. Devuelve exit code (0 ok / 1 con descuadres)."""
    todas_filas: list[list] = []
    descuadres = 0
    generados = 0

    for pdf in pdfs:
        facturas, fecha_imp = parsear_pdf(pdf)
        if not facturas:
            logger.warning(
                "%s: no se encontraron facturas — ¿es un DETALLE DE AUDITORIA Y GLOSAS?", pdf.name
            )
            continue
        fecha_doc = _parse_fecha(fecha_cli or fecha_imp or datetime.now().strftime("%d/%m/%Y"))

        for fac in facturas:
            if fac.total_objetado_pdf is not None and fac.total_extraido != fac.total_objetado_pdf:
                logger.error(
                    "%s: DESCUADRE — glosas extraídas suman $%s pero el PDF dice $%s",
                    fac.cxc,
                    f"{fac.total_extraido:,}",
                    f"{fac.total_objetado_pdf:,}",
                )
                descuadres += 1
            if not fac.glosas:
                logger.info("%s (%s): sin glosas — no se genera Excel", fac.cxc, fac.paciente)
                continue

            filas = filas_objeciones(fac, fecha_doc)
            todas_filas.extend(filas)
            generados += 1
            if consolidado is None:
                destino = salida_dir / f"OBJECIONES_{entidad}_{fac.cxc}.xlsx"
                escribir_excel(filas, destino)
                logger.info(
                    "%s (%s): %d objeciones, total $%s %s → %s",
                    fac.cxc,
                    fac.paciente,
                    len(fac.glosas),
                    f"{fac.total_extraido:,}",
                    "✓ cuadra con el PDF"
                    if fac.total_extraido == fac.total_objetado_pdf
                    else "(sin total en PDF)"
                    if fac.total_objetado_pdf is None
                    else "✗ NO CUADRA",
                    destino,
                )
            else:
                logger.info(
                    "%s (%s): %d objeciones, total $%s",
                    fac.cxc,
                    fac.paciente,
                    len(fac.glosas),
                    f"{fac.total_extraido:,}",
                )

    if consolidado is not None and todas_filas:
        escribir_excel(todas_filas, consolidado)
        logger.info(
            "Consolidado: %d objeciones de %d facturas → %s",
            len(todas_filas),
            generados,
            consolidado,
        )

    if not todas_filas:
        logger.warning("No se extrajo ninguna objeción.")
        return 1
    return 1 if descuadres else 0


def procesar_excel(
    entrada: Path,
    salida_dir: Path | None,
    entidad: str,
    fecha_cli: str | None,
    consolidado: Path | None,
    servicios: Path | None,
    reporte_cruce: Path | None,
) -> int:
    """Pipeline del Excel de glosa inicial. Devuelve exit code (0 ok)."""
    if reporte_cruce is not None and servicios is None:
        logger.error("--reporte-cruce necesita --servicios-dgh (es el detalle de ese cruce).")
        return 2
    if not entrada.is_file():
        logger.error("No existe el archivo de entrada: %s", entrada)
        return 2

    servicios_dgh = None
    if servicios is not None:
        if not servicios.is_file():
            logger.error("No existe el export del DGH: %s", servicios)
            return 2
        logger.info("Leyendo servicios facturados del DGH: %s", servicios.name)
        try:
            servicios_dgh = leer_servicios_dgh(servicios, avisar=logger.warning)
        except ValueError as e:
            logger.error(str(e))
            return 2
        logger.info(
            "  %d renglones de servicio en %d facturas.",
            sum(len(v) for v in servicios_dgh.values()),
            len(servicios_dgh),
        )

    logger.info("Leyendo glosa inicial del Dispensario: %s", entrada.name)
    try:
        objeciones = leer_excel_glosa_inicial(entrada)
    except ValueError as e:
        logger.error(str(e))
        return 2
    if not objeciones:
        logger.error("No se encontró ninguna objeción en %s", entrada.name)
        return 1

    sin_codigo = [o for o in objeciones if not o["codigo"]]
    if sin_codigo:
        logger.warning(
            "  ⚠ %d objeciones sin código de glosa legible: CRNCONOBJ queda vacío (filas %s).",
            len(sin_codigo),
            ", ".join(str(o["fila_excel"]) for o in sin_codigo[:10]),
        )

    fecha_doc = _parse_fecha(fecha_cli or datetime.now().strftime("%d/%m/%Y"))
    trazas: list[dict] = []
    filas = filas_desde_excel(objeciones, fecha_doc, servicios_dgh, trazas)

    if servicios_dgh is not None:
        cuenta = {k: sum(1 for t in trazas if t["confianza"] == k) for k in
                  ("ALTA", "MEDIA", "BAJA", "SIN CRUCE")}  # fmt: skip
        ubicados = cuenta["ALTA"] + cuenta["MEDIA"]
        logger.info(
            "  Cruce contra los servicios del DGH: %d de %d servicios ubicados con "
            "confianza alta/media (%.0f%%).",
            ubicados,
            len(trazas),
            ubicados / (len(trazas) or 1) * 100,
        )
        logger.info(
            "    ALTA=%d  MEDIA=%d  BAJA=%d  SIN CRUCE=%d  → revisar %d.",
            cuenta["ALTA"],
            cuenta["MEDIA"],
            cuenta["BAJA"],
            cuenta["SIN CRUCE"],
            cuenta["BAJA"] + cuenta["SIN CRUCE"],
        )

    # Las reglas fijas del área se comprueban sobre lo que se va a entregar.
    cols = {n: k for k, n in enumerate(ENCABEZADOS)}
    verificar_reglas(
        [
            {
                "factura": f[cols["CRNCXC"]],
                "slnserpro": f[cols["SLNSERPRO"]],
                "ctncencos": f[cols["CTNCENCOS"]],
                "crotipobj": f[cols["CROTIPOBJ"]],
                "codigo_glosa": f[cols["CRNCONOBJ"]],
            }
            for f in filas
        ],
        servicios_dgh,
        avisar=logger.info,
    )

    facturas = sorted({o["cxc"] for o in objeciones})
    if consolidado is not None:
        escribir_excel(filas, consolidado)
        logger.info(
            "Consolidado: %d objeciones de %d facturas → %s",
            len(filas),
            len(facturas),
            consolidado,
        )
    else:
        destino_dir = salida_dir or entrada.parent
        por_factura: dict[str, list[list]] = defaultdict(list)
        for fila in filas:
            por_factura[fila[2]].append(fila)
        for cxc, grupo in sorted(por_factura.items()):
            # Cada archivo lleva UNA factura: su CDCONSEC vuelve a 1.
            grupo = [["1", *fila[1:]] for fila in grupo]
            destino = destino_dir / f"OBJECIONES_{entidad}_{cxc}.xlsx"
            escribir_excel(grupo, destino)
        logger.info("%d archivo(s) en: %s", len(por_factura), destino_dir)

    if reporte_cruce is not None:
        escribir_reporte_cruce(trazas, reporte_cruce, entidad="el Dispensario")
        pendientes = sum(1 for t in trazas if t["aviso"] or t["confianza"] in ("BAJA", "SIN CRUCE"))
        logger.info(
            "Detalle del cruce: %s (%d renglón(es) en la hoja REVISAR).",
            reporte_cruce,
            pendientes,
        )

    logger.info(
        "  Facturas: %d  |  Objeciones: %d  |  Valor glosado total: $%s",
        len(facturas),
        len(filas),
        f"{sum(o['valor'] for o in objeciones):,}",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(
        description="Convierte el PDF de auditoría del Dispensario (AUDITOOL) al Excel OBJECIONES de DGH.",
    )
    fuente = ap.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--pdf", type=Path, help="Un PDF DETALLE DE AUDITORIA Y GLOSAS")
    fuente.add_argument("--carpeta", type=Path, help="Carpeta con varios PDFs")
    fuente.add_argument(
        "--entrada-excel",
        type=Path,
        help="Excel de glosa inicial (FACTURA | VALOR GLOSA INICIAL | SERVICIO OBJETADO "
        "| CODIGO GLOSA INICIAL | DESCRIPCION GLOSA INICIAL)",
    )
    ap.add_argument(
        "--servicios-dgh",
        type=Path,
        default=None,
        help="Export de servicios facturados del DGH: con él SLNSERPRO queda con el "
        "código real del hospital (sólo aplica con --entrada-excel)",
    )
    ap.add_argument(
        "--reporte-cruce",
        type=Path,
        default=None,
        help="Excel de trabajo con el detalle del cruce (hojas CRUCE, REVISAR y RESUMEN). "
        "Requiere --servicios-dgh",
    )
    ap.add_argument(
        "--salida-dir", type=Path, default=None, help="Carpeta de salida (default: la del PDF)"
    )
    ap.add_argument(
        "--consolidado",
        type=Path,
        default=None,
        help="Generar UN SOLO xlsx con todas las facturas en esta ruta",
    )
    ap.add_argument(
        "--entidad",
        default="DISPENSARIO",
        help="Nombre de la entidad para el archivo de salida (default: DISPENSARIO)",
    )
    ap.add_argument(
        "--fecha",
        default=None,
        help="Fecha de la objeción dd/mm/aaaa (default: Fecha Impresión del PDF)",
    )
    args = ap.parse_args(argv)

    if args.entrada_excel:
        return procesar_excel(
            args.entrada_excel,
            salida_dir=args.salida_dir,
            entidad=args.entidad.upper(),
            fecha_cli=args.fecha,
            consolidado=args.consolidado,
            servicios=args.servicios_dgh,
            reporte_cruce=args.reporte_cruce,
        )

    if args.servicios_dgh or args.reporte_cruce:
        logger.error("--servicios-dgh y --reporte-cruce sólo aplican con --entrada-excel.")
        return 2

    if args.pdf:
        pdfs = [args.pdf]
    else:
        pdfs = sorted(args.carpeta.glob("*.pdf")) + sorted(args.carpeta.glob("*.PDF"))
        if not pdfs:
            logger.error("No hay PDFs en %s", args.carpeta)
            return 2

    salida_dir = args.salida_dir or (pdfs[0].parent if args.pdf else args.carpeta)
    return procesar(pdfs, salida_dir, args.entidad.upper(), args.fecha, args.consolidado)


if __name__ == "__main__":
    sys.exit(main())
