"""clasificar_regimen_coosalud.py — Clasifica facturas por regimen y cruza fechas RIPS vs factura.

Lee un Excel con la columna FACTURA (ej. "COOSALUD PARA BRAYAN.xlsx"), busca la
carpeta de soportes de cada factura en el share de facturacion electronica
(\\\\172.16.32.83\\factura_electronica_net22\\<AAAAMM>\\FACTURAS_SALUD\\<factura>\\) y:

 1. Identifica el REGIMEN (Subsidiado / Contributivo) leyendo el tipoUsuario del
    RIPS JSON (Res. 1036/2022 - FEV RIPS). Si la carpeta solo trae RIPS viejos
    en TXT (Res. 3374/2000) usa el archivo US; como ultimo recurso busca el dato
    en el XML de la factura (queda marcado "verificar manualmente").
 2. Copia la carpeta COMPLETA de la factura (XML, PDF, RIPS, CUV) a la carpeta
    maestra de su regimen:  <destino>\\Subsidiado\\  o  <destino>\\Contributivo\\.
    Lo que no se pueda clasificar queda en <destino>\\SIN_CLASIFICAR\\.
 3. Extrae la fecha de ATENCION y de EGRESO del RIPS (consultas, procedimientos,
    urgencias, hospitalizacion, medicamentos, etc.) y la fecha de INGRESO y
    EGRESO del XML de la factura (bloque Interoperabilidad del sector salud o,
    en su defecto, el InvoicePeriod).
 4. Genera el Excel de auditoria con las columnas:
    Factura | Régimen | RIPS_Atencion | RIPS_Egreso | Factura_Ingreso |
    Factura_Egreso | Alerta_Diferencia (SI/NO) + columnas de apoyo.

USO tipico (PowerShell, desde C:\\temp-notas):

    py tools\\clasificar_regimen_coosalud.py `
        --excel "D:\\USUARIO CARTERA\\Downloads\\COOSALUD PARA BRAYAN.xlsx" `
        --destino "D:\\USUARIO CARTERA\\Documents\\COOSALUD\\PARA_BRAYAN" `
        --piloto 5

    * quitar --piloto para procesar todas las facturas.
    * --sin-copiar genera solo el informe (no copia carpetas).
    * --meses 202605,202606 limita la busqueda a esos meses del share.

DEPENDENCIAS:
    py -m pip install openpyxl
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger("clasificar_regimen")

DEFAULT_SHARE = r"\\172.16.32.83\factura_electronica_net22"
RE_MES = re.compile(r"^\d{6}$")

# tipoUsuario del RIPS JSON (Res. 2275/2023, tabla tipoUsuario)
TIPOS_CONTRIBUTIVO = {"01", "02", "03"}
TIPOS_SUBSIDIADO = {"04"}
DESCRIPCION_TIPO = {
    "01": "contributivo cotizante",
    "02": "contributivo beneficiario",
    "03": "contributivo adicional",
    "04": "subsidiado",
}

REGIMEN_SUB = "Subsidiado"
REGIMEN_CON = "Contributivo"
SIN_CLASIFICAR = "SIN_CLASIFICAR"


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades comunes
# ─────────────────────────────────────────────────────────────────────────────


def norm_factura(valor: str) -> str:
    """HUS0000349680 → HUS349680 (tolerante a ceros, guiones y espacios)."""
    v = str(valor or "").strip().upper().replace(" ", "").replace("-", "")
    m = re.match(r"^([A-Z]*)0*(\d+)$", v)
    if m and m.group(2):
        return m.group(1) + m.group(2)
    return v


def _decodificar(crudo: bytes) -> str:
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return crudo.decode(cod)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", errors="ignore")


def parse_fecha(valor: object) -> date | None:
    """Acepta date/datetime, '2026-05-01', '2026-05-01 10:30', '01/05/2026'."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    if not texto:
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Indice del share:  <share>\AAAAMM\FACTURAS_SALUD\<factura>\
# ─────────────────────────────────────────────────────────────────────────────


def indexar_share(base: Path, meses: list[str] | None = None) -> dict[str, list[Path]]:
    """Mapa norm_factura → [carpetas encontradas] (puede haber mas de un mes)."""
    indice: dict[str, list[Path]] = {}
    if not base.is_dir():
        raise OSError(f"No se pudo acceder al share {base} (correr desde un PC del hospital).")
    dirs_mes = sorted(
        d
        for d in base.iterdir()
        if d.is_dir() and RE_MES.match(d.name) and (not meses or d.name in meses)
    )
    if not dirs_mes:
        raise OSError(f"El share {base} no tiene carpetas de mes AAAAMM (o --meses no coincide).")
    for mes in dirs_mes:
        contenedores = [
            c
            for c in mes.iterdir()
            if c.is_dir()
            and c.name.upper().startswith("FACTURAS")
            and c.name.upper() != "FACTURAS_NOTA"
        ]
        for cont in contenedores:
            try:
                hijos = list(cont.iterdir())
            except OSError:
                continue
            for carpeta in hijos:
                if not carpeta.is_dir():
                    continue
                clave = norm_factura(carpeta.name)
                if clave:
                    indice.setdefault(clave, []).append(carpeta)
        logger.info(f"  indexado {mes.name} ({len(indice)} facturas acumuladas)")
    return indice


# ─────────────────────────────────────────────────────────────────────────────
# RIPS — JSON nuevo (Res. 1036/2022) y TXT viejo (Res. 3374/2000)
# ─────────────────────────────────────────────────────────────────────────────

_CLAVES_EGRESO = ("fechaEgreso",)
_CLAVES_NO_ATENCION = {"fechaEgreso", "fechaNacimiento"}
_RE_TXT_RIPS = re.compile(r"^(US|AC|AP|AU|AH|AT|AM|AN|AF)\w*\.(txt|TXT)$")


@dataclass
class DatosRips:
    tipos_usuario: list[str] = field(default_factory=list)
    atencion: date | None = None
    egreso: date | None = None
    egreso_derivado: bool = False  # no habia fechaEgreso: se uso la ultima atencion
    fuente: str = ""
    obs: list[str] = field(default_factory=list)


def _es_rips_json(raw: object) -> bool:
    return isinstance(raw, dict) and isinstance(raw.get("usuarios"), list)


def leer_rips_carpeta(carpeta: Path) -> DatosRips:
    """Busca y consolida los RIPS de la carpeta (JSON nuevo o TXT viejo)."""
    datos = DatosRips()
    inicios: list[date] = []
    egresos: list[date] = []

    # --- RIPS JSON (formato FEV vigente) ---
    for ruta in sorted(carpeta.rglob("*.json")):
        try:
            raw = json.loads(_decodificar(ruta.read_bytes()))
        except (OSError, ValueError):
            continue
        if not _es_rips_json(raw):
            continue  # p.ej. ResultadosDoker_*.json (CUV), no es un RIPS
        datos.fuente = datos.fuente or f"JSON {ruta.name}"
        for u in raw.get("usuarios") or []:
            if not isinstance(u, dict):
                continue
            tipo = str(u.get("tipoUsuario") or "").strip().zfill(2)
            if tipo and tipo != "00":
                datos.tipos_usuario.append(tipo)
            servicios = u.get("servicios") or {}
            if not isinstance(servicios, dict):
                continue
            for lista in servicios.values():
                if not isinstance(lista, list):
                    continue
                for s in lista:
                    if not isinstance(s, dict):
                        continue
                    for clave, valor in s.items():
                        if not clave.lower().startswith("fecha"):
                            continue
                        f = parse_fecha(valor)
                        if f is None:
                            continue
                        if clave in _CLAVES_EGRESO:
                            egresos.append(f)
                        elif clave not in _CLAVES_NO_ATENCION:
                            inicios.append(f)

    # --- RIPS TXT viejos (solo si el JSON no aporto nada) ---
    if not datos.fuente:
        for ruta in sorted(carpeta.rglob("*.txt")):
            if not _RE_TXT_RIPS.match(ruta.name):
                continue
            try:
                texto = _decodificar(ruta.read_bytes())
            except OSError:
                continue
            tipo_archivo = ruta.name[:2].upper()
            datos.fuente = "TXT (RIPS Res. 3374/2000)"
            for linea in texto.splitlines():
                if not linea.strip():
                    continue
                if tipo_archivo == "US":
                    campos = linea.split(",")
                    if len(campos) >= 4:
                        t = campos[3].strip()
                        if t == "1":
                            datos.tipos_usuario.append("01")
                        elif t == "2":
                            datos.tipos_usuario.append("04")
                        elif t:
                            datos.tipos_usuario.append(f"txt:{t}")
                    continue
                fechas_linea = [
                    f
                    for f in (parse_fecha(tok) for tok in re.findall(r"[\d/-]{8,10}", linea))
                    if f is not None
                ]
                if not fechas_linea:
                    continue
                if tipo_archivo in ("AH", "AU"):
                    inicios.append(min(fechas_linea))
                    egresos.append(max(fechas_linea))
                else:
                    inicios.extend(fechas_linea)

    if inicios:
        datos.atencion = min(inicios)
    if egresos:
        datos.egreso = max(egresos)
    elif inicios:
        datos.egreso = max(inicios)
        datos.egreso_derivado = True
        datos.obs.append("sin fechaEgreso en RIPS: se uso la ultima fecha de atencion")
    return datos


def regimen_de_tipos(tipos: list[str]) -> tuple[str, str]:
    """(regimen, detalle). Con usuarios mixtos gana la mayoria y se anota."""
    if not tipos:
        return "", ""
    votos: Counter[str] = Counter()
    for t in tipos:
        if t in TIPOS_CONTRIBUTIVO:
            votos[REGIMEN_CON] += 1
        elif t in TIPOS_SUBSIDIADO:
            votos[REGIMEN_SUB] += 1
        else:
            votos[f"Otro ({t})"] += 1
    regimen, _ = votos.most_common(1)[0]
    unicos = sorted(set(tipos))
    detalle = ", ".join(f"{t} {DESCRIPCION_TIPO.get(t, '')}".strip() for t in unicos)
    if len(votos) > 1:
        detalle += " [MIXTO: " + ", ".join(f"{r}×{n}" for r, n in votos.most_common()) + "]"
    return regimen, detalle


# ─────────────────────────────────────────────────────────────────────────────
# XML de la factura electronica (DIAN, sector salud)
# ─────────────────────────────────────────────────────────────────────────────

_RE_PAR_SALUD = re.compile(
    r"<AdditionalInformation>\s*<Name>([^<]+)</Name>\s*<Value[^>]*>(.*?)</Value>",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class DatosXml:
    ingreso: date | None = None
    egreso: date | None = None
    fuente: str = ""
    regimen_hint: str = ""
    archivo: str = ""


def _texto_xml(ruta: Path) -> str:
    """Lee el XML y des-escapa el Invoice embebido (CDATA o entidades)."""
    try:
        contenido = _decodificar(ruta.read_bytes())
    except OSError:
        return ""
    contenido = contenido.replace("<![CDATA[", "").replace("]]>", "")
    if "&lt;" in contenido:
        contenido = html.unescape(contenido)
    return contenido


def _elegir_xml(carpeta: Path) -> Path | None:
    candidatos = sorted(p for p in carpeta.glob("*.xml") if p.is_file())
    if not candidatos:
        candidatos = sorted(p for p in carpeta.rglob("*.xml") if p.is_file())
    for p in candidatos:
        if p.name.lower().startswith("ad"):
            return p
    for p in candidatos:
        if "<Invoice" in _texto_xml(p):
            return p
    return candidatos[0] if candidatos else None


def analizar_xml_factura(carpeta: Path) -> DatosXml:
    datos = DatosXml()
    ruta = _elegir_xml(carpeta)
    if ruta is None:
        return datos
    datos.archivo = ruta.name
    texto = _texto_xml(ruta)
    if not texto:
        return datos

    # 1) Pares Name/Value del bloque Interoperabilidad (sector salud).
    pares = {
        n.strip().upper(): re.sub(r"\s+", " ", v).strip() for n, v in _RE_PAR_SALUD.findall(texto)
    }
    for nombre, valor in pares.items():
        if "FECHA" not in nombre:
            continue
        f = parse_fecha(valor)
        if f is None:
            continue
        if datos.ingreso is None and ("INGRESO" in nombre or "INICIO" in nombre):
            datos.ingreso = f
            datos.fuente = "Interoperabilidad"
        if datos.egreso is None and ("EGRESO" in nombre or "FIN" in nombre):
            datos.egreso = f
            datos.fuente = "Interoperabilidad"

    # 2) Respaldo: InvoicePeriod de la factura (StartDate/EndDate del bloque).
    if datos.ingreso is None or datos.egreso is None:
        m = re.search(
            r"<(?:\w+:)?InvoicePeriod>(.*?)</(?:\w+:)?InvoicePeriod>",
            texto,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            bloque = m.group(1)
            inicio = re.search(r"<(?:\w+:)?StartDate>([^<]+)<", bloque, re.IGNORECASE)
            fin = re.search(r"<(?:\w+:)?EndDate>([^<]+)<", bloque, re.IGNORECASE)
            uso_periodo = False
            if datos.ingreso is None and inicio:
                datos.ingreso = parse_fecha(inicio.group(1))
                uso_periodo = datos.ingreso is not None
            if datos.egreso is None and fin:
                datos.egreso = parse_fecha(fin.group(1))
                uso_periodo = uso_periodo or datos.egreso is not None
            if uso_periodo:
                datos.fuente = (
                    (datos.fuente + "+InvoicePeriod") if datos.fuente else "InvoicePeriod"
                )

    # 3) Pista de regimen (solo como ULTIMO recurso para clasificar).
    for nombre, valor in pares.items():
        if "REGIMEN" in nombre or "TIPO_USUARIO" in nombre:
            datos.regimen_hint = valor
            break
    if not datos.regimen_hint:
        mayus = texto.upper()
        if "SUBSIDIADO" in mayus and "CONTRIBUTIVO" not in mayus:
            datos.regimen_hint = "SUBSIDIADO"
        elif "CONTRIBUTIVO" in mayus and "SUBSIDIADO" not in mayus:
            datos.regimen_hint = "CONTRIBUTIVO"
    return datos


def regimen_de_hint(hint: str) -> str:
    h = hint.strip().upper()
    if not h:
        return ""
    if "SUBSIDIADO" in h or norm_factura(h) in ("2", "04", "4"):
        return REGIMEN_SUB
    if "CONTRIBUTIVO" in h or norm_factura(h) in ("1", "01", "02", "03", "2", "3"):
        return REGIMEN_CON
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Proceso por factura
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Resultado:
    factura: str
    regimen: str = ""
    rips_atencion: date | None = None
    rips_egreso: date | None = None
    fact_ingreso: date | None = None
    fact_egreso: date | None = None
    alerta: str = "SIN DATOS"
    detalle_dif: str = ""
    tipos_usuario: str = ""
    fuente_regimen: str = ""
    fuente_fechas_xml: str = ""
    origen: str = ""
    destino: str = ""
    copiados: int = 0
    obs: list[str] = field(default_factory=list)


def _comparar_fechas(r: Resultado) -> None:
    fechas = (r.rips_atencion, r.rips_egreso, r.fact_ingreso, r.fact_egreso)
    if any(f is None for f in fechas):
        r.alerta = "SIN DATOS"
        faltan = [
            n
            for n, f in zip(
                ("RIPS_Atencion", "RIPS_Egreso", "Factura_Ingreso", "Factura_Egreso"), fechas
            )
            if f is None
        ]
        r.detalle_dif = "faltan: " + ", ".join(faltan)
        return
    difs = []
    if r.rips_atencion != r.fact_ingreso:
        dias = (r.fact_ingreso - r.rips_atencion).days  # type: ignore[operator]
        difs.append(f"atencion/ingreso difieren {abs(dias)} dia(s)")
    if r.rips_egreso != r.fact_egreso:
        dias = (r.fact_egreso - r.rips_egreso).days  # type: ignore[operator]
        difs.append(f"egreso difiere {abs(dias)} dia(s)")
    r.alerta = "SI" if difs else "NO"
    r.detalle_dif = "; ".join(difs)


def procesar_factura(
    factura: str,
    carpetas: list[Path],
    destino: Path,
    copiar: bool,
) -> Resultado:
    r = Resultado(factura=factura)
    if not carpetas:
        r.regimen = "NO_ENCONTRADA"
        r.obs.append("la factura no aparece en el share")
        return r
    # Si esta en varios meses se usa la carpeta del mes mas reciente.
    carpeta = sorted(carpetas, key=lambda p: str(p))[-1]
    r.origen = str(carpeta)
    if len(carpetas) > 1:
        r.obs.append(f"aparece en {len(carpetas)} carpetas del share; se uso la mas reciente")

    rips = leer_rips_carpeta(carpeta)
    xml = analizar_xml_factura(carpeta)

    r.rips_atencion, r.rips_egreso = rips.atencion, rips.egreso
    r.fact_ingreso, r.fact_egreso = xml.ingreso, xml.egreso
    r.tipos_usuario = ", ".join(sorted(set(rips.tipos_usuario)))
    r.fuente_fechas_xml = xml.fuente or (
        "sin fechas en " + xml.archivo if xml.archivo else "sin XML"
    )
    r.obs.extend(rips.obs)

    regimen, detalle = regimen_de_tipos(rips.tipos_usuario)
    if regimen in (REGIMEN_SUB, REGIMEN_CON):
        r.regimen = regimen
        r.fuente_regimen = rips.fuente
        if detalle:
            r.obs.append("tipoUsuario: " + detalle)
    elif regimen:
        r.regimen = regimen
        r.fuente_regimen = rips.fuente
        r.obs.append("tipoUsuario fuera de contributivo/subsidiado: " + detalle)
    else:
        desde_xml = regimen_de_hint(xml.regimen_hint)
        if desde_xml:
            r.regimen = desde_xml
            r.fuente_regimen = "XML (verificar manualmente)"
            r.obs.append(f"regimen tomado del XML ('{xml.regimen_hint}'): sin RIPS legible")
        else:
            r.regimen = SIN_CLASIFICAR
            r.obs.append("sin RIPS legible ni pista de regimen en el XML")

    _comparar_fechas(r)

    if copiar:
        subcarpeta = r.regimen if r.regimen in (REGIMEN_SUB, REGIMEN_CON) else SIN_CLASIFICAR
        destino_fac = destino / subcarpeta / carpeta.name
        try:
            shutil.copytree(carpeta, destino_fac, dirs_exist_ok=True)
            r.destino = str(destino_fac)
            r.copiados = sum(1 for p in destino_fac.rglob("*") if p.is_file())
        except OSError as exc:
            r.obs.append(f"NO se pudo copiar: {exc}")
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Entrada (Excel de facturas) y salida (Excel de auditoria)
# ─────────────────────────────────────────────────────────────────────────────


def leer_facturas_excel(ruta: Path, hoja: str | None, columna: str) -> list[str]:
    from openpyxl import load_workbook

    wb = load_workbook(ruta, read_only=True, data_only=True)
    try:
        nombre = hoja or wb.sheetnames[0]
        if nombre not in wb.sheetnames:
            objetivo = nombre.strip().casefold()
            real = next((s for s in wb.sheetnames if s.strip().casefold() == objetivo), None)
            if real is None:
                raise ValueError(f"El Excel no tiene la hoja '{nombre}'. Hojas: {wb.sheetnames}")
            nombre = real
        ws = wb[nombre]
        filas = ws.iter_rows(values_only=True)
        encabezado = next(filas, None)
        if not encabezado:
            raise ValueError("La hoja esta vacia.")
        objetivo = columna.strip().casefold()
        idx = next(
            (i for i, c in enumerate(encabezado) if str(c or "").strip().casefold() == objetivo),
            None,
        )
        if idx is None:
            raise ValueError(f"No encontre la columna '{columna}'. Encabezados: {list(encabezado)}")
        facturas: list[str] = []
        vistas: set[str] = set()
        for fila in filas:
            valor = str(fila[idx] or "").strip() if idx < len(fila) else ""
            if not valor:
                continue
            clave = norm_factura(valor)
            if clave in vistas:
                continue
            vistas.add(clave)
            facturas.append(valor)
        return facturas
    finally:
        wb.close()


ENCABEZADOS = (
    "Factura",
    "Régimen",
    "RIPS_Atencion",
    "RIPS_Egreso",
    "Factura_Ingreso",
    "Factura_Egreso",
    "Alerta_Diferencia",
    "Detalle_Diferencia",
    "Tipo_Usuario_RIPS",
    "Fuente_Regimen",
    "Fuente_Fechas_Factura",
    "Archivos_Copiados",
    "Carpeta_Origen",
    "Carpeta_Destino",
    "Observaciones",
)


def escribir_auditoria(resultados: list[Resultado], salida: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "AUDITORIA"
    ws.append(list(ENCABEZADOS))
    for celda in ws[1]:
        celda.font = Font(bold=True)
    rojo = PatternFill("solid", start_color="FFC7CE")
    verde = PatternFill("solid", start_color="C6EFCE")
    for r in resultados:
        ws.append(
            [
                r.factura,
                r.regimen,
                r.rips_atencion,
                r.rips_egreso,
                r.fact_ingreso,
                r.fact_egreso,
                r.alerta,
                r.detalle_dif,
                r.tipos_usuario,
                r.fuente_regimen,
                r.fuente_fechas_xml,
                r.copiados or "",
                r.origen,
                r.destino,
                " | ".join(r.obs),
            ]
        )
        fila = ws.max_row
        for col in ("C", "D", "E", "F"):
            ws[f"{col}{fila}"].number_format = "DD/MM/YYYY"
        celda_alerta = ws[f"G{fila}"]
        if r.alerta == "SI":
            celda_alerta.fill = rojo
        elif r.alerta == "NO":
            celda_alerta.fill = verde
    anchos = (16, 14, 13, 13, 14, 14, 16, 34, 18, 22, 20, 16, 52, 52, 60)
    for i, ancho in enumerate(anchos, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = ancho
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(ENCABEZADOS)).column_letter}{ws.max_row}"
    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--excel", type=Path, required=True, help="Excel con la columna FACTURA.")
    parser.add_argument("--hoja", type=str, default=None, help="Hoja a leer (default: la primera).")
    parser.add_argument("--columna", type=str, default="FACTURA", help="Columna de facturas.")
    parser.add_argument(
        "--share", type=Path, default=Path(DEFAULT_SHARE), help="Raiz del share de facturacion."
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=Path(r"D:\USUARIO CARTERA\Documents\COOSALUD\CLASIFICADO_REGIMEN"),
        help="Carpeta donde crear Subsidiado\\ y Contributivo\\.",
    )
    parser.add_argument(
        "--salida", type=Path, default=None, help="Excel de auditoria (default: en --destino)."
    )
    parser.add_argument(
        "--meses", type=str, default="", help="Limitar la busqueda a meses AAAAMM (por coma)."
    )
    parser.add_argument("--piloto", type=int, default=0, help="Procesar solo las primeras N.")
    parser.add_argument(
        "--sin-copiar", action="store_true", help="Solo el informe: no copia carpetas."
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    try:
        import openpyxl  # noqa: F401
    except ImportError:
        sys.stderr.write("ERROR: falta openpyxl. Instalalo con: py -m pip install openpyxl\n")
        return 2

    if not args.excel.is_file():
        logger.error(f"No existe el Excel: {args.excel}")
        return 1
    try:
        facturas = leer_facturas_excel(args.excel, args.hoja, args.columna)
    except ValueError as exc:
        logger.error(str(exc))
        return 1
    if args.piloto > 0:
        facturas = facturas[: args.piloto]
        logger.info(f"PILOTO: solo las primeras {len(facturas)} facturas")
    logger.info(f"Facturas a procesar: {len(facturas)}")

    meses = [m.strip() for m in args.meses.split(",") if m.strip()] or None
    logger.info(f"Indexando el share {args.share} ...")
    try:
        indice = indexar_share(args.share, meses)
    except OSError as exc:
        logger.error(str(exc))
        return 1
    logger.info(f"Indice listo: {len(indice)} carpetas de factura en el share.")

    salida = args.salida or (args.destino / "AUDITORIA_FECHAS_REGIMEN.xlsx")
    resultados: list[Resultado] = []
    for i, fac in enumerate(facturas, 1):
        r = procesar_factura(
            fac, indice.get(norm_factura(fac), []), args.destino, not args.sin_copiar
        )
        resultados.append(r)
        rango_rips = (
            f"{r.rips_atencion:%d/%m}–{r.rips_egreso:%d/%m}"
            if r.rips_atencion and r.rips_egreso
            else "—"
        )
        rango_fe = (
            f"{r.fact_ingreso:%d/%m}–{r.fact_egreso:%d/%m}"
            if r.fact_ingreso and r.fact_egreso
            else "—"
        )
        logger.info(
            f"[{i}/{len(facturas)}] {fac} → {r.regimen or '?'} | RIPS {rango_rips} | FE {rango_fe} | alerta {r.alerta}"
        )

    escribir_auditoria(resultados, salida)

    conteo = Counter(r.regimen for r in resultados)
    alertas = sum(1 for r in resultados if r.alerta == "SI")
    logger.info("")
    logger.info("========== RESUMEN ==========")
    for regimen, n in conteo.most_common():
        logger.info(f"  {regimen}: {n}")
    logger.info(f"  Con diferencia de fechas (Alerta SI): {alertas}")
    logger.info(f"  Excel de auditoria: {salida}")
    if not args.sin_copiar:
        logger.info(f"  Carpetas copiadas bajo: {args.destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
