"""Las fechas de atención que el hospital DECLARÓ, para contrastar el RIPS.

POR QUÉ EXISTE (08-09-2026, con la HUS559324 en la mano). Hasta ahora el
sistema solo tenía las fechas del RIPS y avisaba, con razón, que «no hay
fechas declaradas con qué contrastarlas». Resulta que sí las hay, y en la
misma carpeta del servidor de facturación electrónica:

  · **El XML de la factura electrónica** (`fv….xml`, o dentro del
    `ad….xml`): el bloque `InvoicePeriod` trae la fecha —y la hora— de
    inicio y fin de la atención. Es lo que el hospital le declaró a la DIAN.
  · **El resultado del validador del Ministerio** (`ResultadosMSPS_….json`
    o `ResultadosDoker_….json`): trae `PeriodoAtencion` con las mismas dos
    fechas, ya validadas para expedir el CUV.

Se leen las dos y se prefiere el XML, porque es el documento que soporta el
cobro; el del validador queda como respaldo y como segunda opinión.

CASO QUE LO ORIGINÓ. La factura HUS559324 salió marcada como prescrita y
Yesid quiso comprobarlo. Las tres fuentes dijeron lo mismo —RIPS
`2025-02-13 06:55`, XML `InvoicePeriod 2025-02-13`, validador
`PeriodoAtencion 2025-02-13`— contra una factura emitida el `2026-09-04`.
La cuenta llevaba 18 meses y 22 días. La alerta era correcta.

Igual que el resto del módulo: si el archivo no está o no se entiende, se
dice el motivo. Nunca se inventa una fecha.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.services.rips_localizador import SUBCARPETAS, carpetas_candidatas

# El XML de la factura de venta y el documento adjunto que la envuelve.
_RE_XML_FACTURA = re.compile(r"^(fv|ad)[^/\\]*\.xml$", re.IGNORECASE)
# El resultado del validador del Ministerio que expide el CUV.
_RE_RESULTADO = re.compile(r"^resultados(msps|doker)[^/\\]*\.json$", re.IGNORECASE)
# El PDF impreso de la factura: es el ÚNICO documento que trae la fecha de
# egreso de verdad cuando la atención fueron varias sesiones (caso HUS559324).
_RE_PDF_FACTURA = re.compile(r"^(fv|fev)[^/\\]*\.pdf$", re.IGNORECASE)

# «Fec Ingreso 13 feb. 2025 06:54 a. m.  Fec Egreso 14 mar. 2025 05:29 p. m.»
_MESES = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_RE_FEC = r"(\d{{1,2}})\s+([a-zA-Záéíóú]{{3,10}})\.?\s+(\d{{4}})"
_RE_PDF_INGRESO = re.compile(r"Fec\.?\s*Ingreso\s+" + _RE_FEC.format(), re.IGNORECASE)
_RE_PDF_EGRESO = re.compile(r"Fec\.?\s*Egreso\s+" + _RE_FEC.format(), re.IGNORECASE)

# El período de atención dentro del XML (UBL). El `ad….xml` trae la factura
# embebida, así que el mismo patrón sirve para los dos archivos.
_RE_PERIODO = re.compile(r"<cac:InvoicePeriod>(.*?)</cac:InvoicePeriod>", re.IGNORECASE | re.DOTALL)
_RE_INICIO = re.compile(r"<cbc:StartDate>\s*([0-9-]{8,10})\s*</cbc:StartDate>", re.IGNORECASE)
_RE_FIN = re.compile(r"<cbc:EndDate>\s*([0-9-]{8,10})\s*</cbc:EndDate>", re.IGNORECASE)

# Un XML de factura pesa unos cientos de KB. Más que esto no se abre.
MAX_BYTES_XML = 30 * 1024 * 1024


@dataclass(frozen=True)
class FechasDeclaradas:
    """Lo que el hospital declaró de la atención, y de dónde salió."""

    fecha_ingreso: Optional[datetime] = None
    fecha_egreso: Optional[datetime] = None
    origen: str = ""  # "factura electrónica" | "validador del Ministerio"
    archivo: str = ""
    problema: str = ""

    @property
    def completas(self) -> bool:
        return self.fecha_ingreso is not None and self.fecha_egreso is not None

    def a_dict(self) -> dict[str, Any]:
        return {
            "fecha_ingreso": self.fecha_ingreso.isoformat() if self.fecha_ingreso else None,
            "fecha_egreso": self.fecha_egreso.isoformat() if self.fecha_egreso else None,
            "origen": self.origen,
            "archivo": self.archivo,
            "problema": self.problema,
            "completas": self.completas,
        }


def _a_fecha(texto: Any) -> Optional[datetime]:
    if not texto:
        return None
    crudo = str(texto).strip().replace("T", " ").split("+")[0].strip()
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(crudo[: len(formato) + 4], formato)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(crudo)
    except ValueError:
        return None


def _texto_de(ruta: Path) -> tuple[str, str]:
    """Lee el archivo tolerando la codificación. Devuelve (texto, problema)."""
    try:
        if not ruta.is_file():
            return "", f"no se encontró el archivo: {ruta.name}"
        if ruta.stat().st_size > MAX_BYTES_XML:
            return "", f"{ruta.name} pesa demasiado: no se abrió"
        crudo = ruta.read_bytes()
    except OSError as e:
        return "", f"no se pudo leer {ruta.name}: {e}"
    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return crudo.decode(codificacion), ""
        except UnicodeDecodeError:
            continue
    return "", f"{ruta.name} no se pudo interpretar"


def fechas_de_xml(ruta: str | Path) -> FechasDeclaradas:
    """El `InvoicePeriod` del XML de la factura electrónica."""
    p = Path(ruta)
    texto, problema = _texto_de(p)
    if problema:
        return FechasDeclaradas(archivo=p.name, problema=problema)

    for bloque in _RE_PERIODO.findall(texto):
        ini, fin = _RE_INICIO.search(bloque), _RE_FIN.search(bloque)
        if ini and fin:
            return FechasDeclaradas(
                fecha_ingreso=_a_fecha(ini.group(1)),
                fecha_egreso=_a_fecha(fin.group(1)),
                origen="factura electrónica",
                archivo=p.name,
            )
    return FechasDeclaradas(
        archivo=p.name,
        problema=f"{p.name} no trae el período de atención (InvoicePeriod)",
    )


def fechas_de_resultado_validador(ruta: str | Path) -> FechasDeclaradas:
    """El `PeriodoAtencion` del resultado del validador del Ministerio."""
    p = Path(ruta)
    texto, problema = _texto_de(p)
    if problema:
        return FechasDeclaradas(archivo=p.name, problema=problema)
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return FechasDeclaradas(archivo=p.name, problema=f"{p.name} no se pudo leer como JSON")

    periodo = datos.get("PeriodoAtencion") if isinstance(datos, dict) else None
    if not isinstance(periodo, dict):
        return FechasDeclaradas(archivo=p.name, problema=f"{p.name} no trae PeriodoAtencion")
    return FechasDeclaradas(
        fecha_ingreso=_a_fecha(periodo.get("FechaInicio")),
        fecha_egreso=_a_fecha(periodo.get("FechaFin")),
        origen="validador del Ministerio",
        archivo=p.name,
    )


def _fecha_larga(dia: str, mes: str, anio: str) -> Optional[datetime]:
    """«14 mar. 2025» → datetime(2025, 3, 14). Devuelve None si no cuadra."""
    numero = _MESES.get(mes[:3].lower())
    if not numero:
        return None
    try:
        return datetime(int(anio), numero, int(dia))
    except ValueError:
        return None


def fechas_de_pdf(ruta: str | Path) -> FechasDeclaradas:
    """El «Fec Ingreso / Fec Egreso» impreso en la factura del hospital.

    Es la fuente que hay que creerle cuando la atención fueron varias
    sesiones: el RIPS trae solo la primera y el XML copia esa misma, pero el
    PDF sí imprime el día en que el paciente salió.
    """
    p = Path(ruta)
    try:
        if not p.is_file():
            return FechasDeclaradas(archivo=p.name, problema=f"no se encontró el archivo: {p.name}")
        from PyPDF2 import PdfReader

        texto = "".join(pag.extract_text() or "" for pag in PdfReader(str(p)).pages)
    except Exception as e:  # PDF cifrado, roto, o sin la librería
        return FechasDeclaradas(
            archivo=p.name, problema=f"no se pudo leer {p.name}: {str(e)[:150]}"
        )

    texto = re.sub(r"[ \t]+", " ", texto)
    ing, egr = _RE_PDF_INGRESO.search(texto), _RE_PDF_EGRESO.search(texto)
    if not (ing and egr):
        return FechasDeclaradas(
            archivo=p.name, problema=f"{p.name} no imprime «Fec Ingreso» y «Fec Egreso»"
        )
    return FechasDeclaradas(
        fecha_ingreso=_fecha_larga(*ing.groups()),
        fecha_egreso=_fecha_larga(*egr.groups()),
        origen="factura impresa",
        archivo=p.name,
    )


def _archivos_en(carpeta: Path, patron: re.Pattern) -> list[Path]:
    hallados: list[Path] = []
    for sub in SUBCARPETAS:
        destino = carpeta / sub if sub else carpeta
        try:
            if not destino.is_dir():
                continue
            hallados += [
                h for h in sorted(destino.iterdir()) if h.is_file() and patron.match(h.name)
            ]
        except OSError:
            continue
    return hallados


def buscar(
    factura: str,
    fecha_factura: Any = None,
    raiz: Optional[str] = None,
    meses_alrededor: int = 1,
) -> FechasDeclaradas:
    """Las fechas declaradas de una factura, buscándolas en su carpeta.

    ORDEN DE CONFIANZA, y el porqué de cada puesto:

      1. **La factura impresa (PDF)**. Es la única que trae el día en que el
         paciente salió cuando la atención fueron varias sesiones.
      2. **El XML de la factura electrónica**. Es el documento legal, pero su
         `InvoicePeriod` copia la fecha de la primera atención: en la
         HUS559324 decía que la atención empezó y terminó el mismo minuto,
         cuando fueron 20 sesiones en un mes.
      3. **El resultado del validador del Ministerio**, que lee del XML y por
         tanto arrastra el mismo error.

    Si el PDF y el XML se contradicen, se devuelve el PDF y la contradicción
    queda escrita en `problema`: es un reparo que hay que corregir en
    facturación antes de que lo glose el ADRES.
    """
    carpetas, periodos, problema = carpetas_candidatas(
        factura, fecha_factura, raiz, meses_alrededor
    )
    if problema:
        return FechasDeclaradas(problema=problema)

    del_pdf = del_xml = del_validador = None
    for carpeta in carpetas:
        for ruta in _archivos_en(carpeta, _RE_PDF_FACTURA):
            leidas = fechas_de_pdf(ruta)
            if leidas.completas and del_pdf is None:
                del_pdf = leidas
        for ruta in _archivos_en(carpeta, _RE_XML_FACTURA):
            leidas = fechas_de_xml(ruta)
            if leidas.completas and del_xml is None:
                del_xml = leidas
        for ruta in _archivos_en(carpeta, _RE_RESULTADO):
            leidas = fechas_de_resultado_validador(ruta)
            if leidas.completas and del_validador is None:
                del_validador = leidas
        if del_pdf and del_xml:
            break

    mejor = del_pdf or del_xml or del_validador
    if mejor is None:
        return FechasDeclaradas(
            problema=(
                f"No se encontró la factura {factura} en el servidor "
                f"(se miraron los períodos {', '.join(periodos)})."
            )
        )

    # La contradicción que hay que ver: el XML dice una fecha de salida y la
    # factura impresa otra. Se reporta sobre la del PDF, que es la buena.
    if del_pdf and del_xml and del_pdf.fecha_egreso != del_xml.fecha_egreso:
        return FechasDeclaradas(
            fecha_ingreso=del_pdf.fecha_ingreso,
            fecha_egreso=del_pdf.fecha_egreso,
            origen=del_pdf.origen,
            archivo=del_pdf.archivo,
            problema=(
                "La factura impresa y el XML no dicen lo mismo del egreso: "
                f"el PDF dice {del_pdf.fecha_egreso:%d/%m/%Y} y el XML "
                f"{del_xml.fecha_egreso:%d/%m/%Y}. El XML es el que viaja al "
                "ADRES: hay que corregirlo en facturación."
            ),
        )
    return mejor
