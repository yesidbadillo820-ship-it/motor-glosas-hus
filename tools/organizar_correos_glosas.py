"""organizar_correos_glosas.py — Archiva correos de glosas/devoluciones en el servidor Z:.

Lee la bandeja institucional (glosasydevoluciones@hus.gov.co) por IMAP, clasifica
cada correo en INICIAL / RATIFICADAS / DEVOLUCIONES / CONCILIACIONES (o 0-REVISAR
si no hay certeza), detecta la entidad pagadora (DISPENSARIO/AUDITOOL, AXA,
SEGUROS BOLIVAR, SALUD MIA, ...) y guarda en la estructura del servidor de glosas:

    <base>\\<AÑO>\\<MM MES>\\<DD>\\<CATEGORÍA>\\<ENTIDAD OK>\\
        ├── <ENTIDAD> <n> OK.pdf      (el correo impreso a PDF, como el proceso manual)
        └── <adjuntos originales>     (PDF, Excel, CSV, ZIP, ...)

La fecha de carpeta es la fecha de LLEGADA del correo (hora Colombia), no la de
ejecución. Nunca sobreescribe archivos (agrega " (2)") y nunca borra ni mueve
correos: solo les agrega la etiqueta de Gmail "Archivado-Glosas" al procesarlos.
La deduplicación real se lleva en un archivo de estado (Message-ID ya procesados),
así que re-ejecutar es seguro.

USO RÁPIDO
----------

    # Simulacro: muestra qué archivaría sin tocar nada
    py organizar_correos_glosas.py --dry-run

    # Corrida real (últimos 3 días de la bandeja)
    py organizar_correos_glosas.py

    # Backfill desde una fecha, hasta 500 correos
    py organizar_correos_glosas.py --desde 2026-07-01 --max 500

    # Probar en una carpeta local sin unidad Z:
    py organizar_correos_glosas.py --base C:\\pruebas\\glosas --dry-run

CREDENCIALES (una sola vez, en el equipo que ejecuta):

    setx GLOSAS_IMAP_USER glosasydevoluciones@hus.gov.co
    setx GLOSAS_IMAP_PASSWORD <contraseña de aplicación de 16 letras>

La contraseña de aplicación se genera en https://myaccount.google.com/apppasswords
(requiere verificación en dos pasos activa). Después de setx, cerrar y reabrir
la consola. Ver tools/README_organizar_correos_glosas.md para el paso a paso.

DEPENDENCIAS
------------
- Python 3.11+
- reportlab (pip install reportlab) para el PDF del correo. Si hay Microsoft Edge
  o Chrome instalado, se usa el navegador en modo headless (mejor fidelidad) y
  reportlab queda de respaldo.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import csv
import email
import email.header
import email.message
import email.utils
import hashlib
import imaplib
import json
import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.sax.saxutils import escape as _escape_xml

DEFAULT_BASE = (
    r"Z:\SERVIDOR GLOSAS\F\RECEPCIÓN DE GLOSAS (NO ELIMINAR CARPETA)"
    r"\03-GLOSAS ESCANEADAS 2.0 (NO ELIMINAR CARPETA )"
)
DEFAULT_CONTROL = "00-CONTROL AUTOMATICO"
DEFAULT_CARPETA_IMAP = "INBOX"
DEFAULT_DIAS = 3
DEFAULT_MAX = 200

MESES_ES = (
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)
MESES_IMAP = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Colombia no tiene horario de verano: UTC-5 fijo.
TZ_COLOMBIA = timezone(timedelta(hours=-5))

# Sanitizador para nombres de archivo en Windows (mismo patrón que otros tools/)
RE_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RE_RADICADO = re.compile(r"RADICADO\s+(?:N[O0]?\.?\s*)?(\d+)")
RE_DOMINIO = re.compile(r"@([\w.-]+)")

EXTENSIONES_OMITIDAS = {".p7s", ".asc"}  # firmas S/MIME, sin valor documental

logger = logging.getLogger("organizar_correos")

# ─── Configuración por defecto (sobreescribible con --config archivo.json) ──

CONFIG_DEFECTO: dict = {
    "etiqueta_gmail": "Archivado-Glosas",
    "categoria_revision": "0-REVISAR",
    "revisar_si_glosa_y_devolucion": True,
    "min_bytes_imagen_inline": 15000,
    "ignorar_asuntos": [
        "CARGUE EXITOSO",
        "ERRORES EN EL PROCESAMIENTO DEL ZIP",
    ],
    "categorias": [
        {"nombre": "CONCILIACIONES", "patrones": ["CONCILIACION"]},
        {"nombre": "RATIFICADAS", "patrones": ["RATIFICA"]},
        {"nombre": "DEVOLUCIONES", "patrones": ["DEVOLUCION", "DEVUELTA", "\\bDEV[O0]?\\d"]},
        {"nombre": "INICIAL", "patrones": ["GLOSA", "OBJECION", "AUDITORIA"]},
    ],
    "entidades": [
        {
            "carpeta": "DISPENSARIO",
            "remitente": ["@TOOL\\.COM\\.CO", "AUDITOOL"],
            "asunto": ["AUDITOOL", "SANIDAD MILITAR", "DISPENSARIO"],
            "adjuntos": [],
        },
        {
            "carpeta": "AXA",
            "remitente": ["GRUPOMOK", "COLPATRIA", "\\bAXA\\b"],
            "asunto": ["\\bAXA\\b", "COLPATRIA"],
            "adjuntos": [],
        },
        {
            "carpeta": "SEGUROS BOLIVAR",
            "remitente": ["SEGUROSBOLIVAR", "BOLIVAR"],
            "asunto": ["SEGUROS BOLIVAR", "BOLIVAR"],
            "adjuntos": [],
        },
        {
            "carpeta": "SALUD MIA",
            "remitente": ["SALUDMIA"],
            "asunto": ["SALUD MIA"],
            "adjuntos": [],
        },
        {
            "carpeta": "FACTRAMED",
            "remitente": ["FACTRAMED"],
            "asunto": ["FACTRAMED"],
            "adjuntos": [],
        },
    ],
    "plantillas": {
        "carpeta_entidad": "{entidad} OK",
        "pdf_correo": {
            "DEVOLUCIONES": "{asunto} OK",
            "*": "{entidad} {consecutivo} OK",
        },
    },
}


# ─── Utilidades ──────────────────────────────────────────────────────────────


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    # Consolas cmd con codepage limitada: nunca abortar por un carácter raro
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
        )
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def sanitizar(nombre: str) -> str:
    """Reemplaza caracteres inválidos de Windows y colapsa espacios."""
    limpio = RE_INVALIDOS.sub("_", nombre)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    return limpio.rstrip(". ")


def _quitar_diacriticos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _normalizar(texto: str) -> str:
    """MAYÚSCULAS sin tildes, para comparar contra los patrones de config."""
    return _quitar_diacriticos(texto).upper()


def _acotar(texto: str, max_len: int) -> str:
    return texto if len(texto) <= max_len else texto[:max_len].rstrip()


def decodificar_encabezado(valor: str | None) -> str:
    """Decodifica encabezados MIME (=?UTF-8?Q?...?=) a texto plano."""
    if not valor:
        return ""
    partes: list[str] = []
    for texto, charset in email.header.decode_header(valor):
        if isinstance(texto, bytes):
            partes.append(texto.decode(charset or "utf-8", errors="replace"))
        else:
            partes.append(texto)
    return re.sub(r"\s+", " ", "".join(partes)).strip()


def cargar_config(ruta: Path | None) -> dict:
    """Config por defecto, con las claves presentes en el JSON del usuario encima."""
    config = json.loads(json.dumps(CONFIG_DEFECTO))  # copia profunda
    if ruta is None:
        return config
    try:
        propia = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.stderr.write(f"ERROR: no existe el archivo de config {ruta}\n")
        sys.exit(2)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"ERROR: el JSON de config {ruta} no es válido: {exc}\n")
        sys.exit(2)
    if not isinstance(propia, dict):
        sys.stderr.write(f"ERROR: el config {ruta} debe ser un objeto JSON\n")
        sys.exit(2)
    config.update(propia)
    return config


# ─── Clasificación ───────────────────────────────────────────────────────────


def debe_ignorarse(asunto: str, config: dict) -> bool:
    texto = _normalizar(asunto)
    return any(re.search(patron, texto) for patron in config.get("ignorar_asuntos", []))


def clasificar_categoria(asunto: str, nombres_adjuntos: list[str], config: dict) -> tuple[str, str]:
    """Devuelve (categoría, motivo). Solo mira asunto y nombres de adjuntos:
    el cuerpo trae boilerplate (firmas que mencionan conciliación/ratificadas)
    que produce falsos positivos."""
    texto = _normalizar(asunto + " " + " ".join(nombres_adjuntos))
    coincidencias: list[tuple[str, str]] = []
    for regla in config["categorias"]:
        for patron in regla["patrones"]:
            if re.search(patron, texto):
                coincidencias.append((regla["nombre"], patron))
                break
    nombres = {nombre for nombre, _ in coincidencias}
    if config.get("revisar_si_glosa_y_devolucion", True) and {"DEVOLUCIONES", "INICIAL"} <= nombres:
        return config["categoria_revision"], "GLOSA+DEVOLUCION en el mismo correo"
    if coincidencias:
        nombre, patron = coincidencias[0]
        return nombre, f"patrón '{patron}'"
    return config["categoria_revision"], "sin coincidencia de categoría"


def detectar_entidad(
    remitente: str, asunto: str, nombres_adjuntos: list[str], config: dict
) -> tuple[str, bool]:
    """Devuelve (carpeta de entidad, identificada). Si ninguna regla coincide,
    usa el dominio del remitente como carpeta para no perder el correo."""
    rem = _normalizar(remitente)
    asu = _normalizar(asunto)
    adj = _normalizar(" ".join(nombres_adjuntos))
    for regla in config["entidades"]:
        campos = (
            (regla.get("remitente", []), rem),
            (regla.get("asunto", []), asu),
            (regla.get("adjuntos", []), adj),
        )
        for patrones, texto in campos:
            if any(re.search(p, texto) for p in patrones):
                return regla["carpeta"], True
    dominio = RE_DOMINIO.search(rem)
    if dominio:
        return dominio.group(1).strip(".").upper(), False
    return "SIN REMITENTE", False


def extraer_radicado(asunto: str) -> str:
    coincidencia = RE_RADICADO.search(_normalizar(asunto))
    return coincidencia.group(1) if coincidencia else ""


# ─── Extracción de partes del correo ─────────────────────────────────────────


class _ExtractorTextoHtml(HTMLParser):
    _BLOQUES = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "hr"}
    _OMITIR = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._trozos: list[str] = []
        self._omitiendo = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self._OMITIR:
            self._omitiendo += 1
        elif tag in self._BLOQUES:
            self._trozos.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._OMITIR and self._omitiendo:
            self._omitiendo -= 1
        elif tag in self._BLOQUES:
            self._trozos.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._omitiendo:
            self._trozos.append(data)

    @property
    def texto(self) -> str:
        crudo = "".join(self._trozos)
        lineas = [re.sub(r"[ \t]+", " ", ln).strip() for ln in crudo.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()


def extraer_texto_html(html: str) -> str:
    parser = _ExtractorTextoHtml()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # HTML roto: mejor algo que nada
        pass
    return parser.texto


def _texto_de_parte(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extraer_partes(
    msg: email.message.Message, config: dict
) -> tuple[str, str, dict[str, tuple[str, bytes]], list[tuple[str, bytes]]]:
    """Devuelve (texto_plano, html, imagenes_inline_por_cid, adjuntos).

    - imagenes_inline_por_cid: para incrustar en el PDF del correo (data URI).
    - adjuntos: [(nombre, contenido)] a guardar en la carpeta destino. Se omiten
      logos de firma (imágenes inline pequeñas) y firmas S/MIME.
    """
    min_inline = int(config.get("min_bytes_imagen_inline", 15000))
    texto_plano, html = "", ""
    inlines: dict[str, tuple[str, bytes]] = {}
    adjuntos: list[tuple[str, bytes]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        ctype = part.get_content_type()
        disposicion = (part.get_content_disposition() or "").lower()
        nombre = decodificar_encabezado(part.get_filename())
        contenido = part.get_payload(decode=True) or b""
        content_id = (part.get("Content-ID") or "").strip("<> \t")
        if content_id and ctype.startswith("image/"):
            inlines[content_id] = (ctype, contenido)
        if not nombre:
            if ctype == "text/plain" and disposicion != "attachment" and not texto_plano:
                texto_plano = _texto_de_parte(part)
            elif ctype == "text/html" and disposicion != "attachment" and not html:
                html = _texto_de_parte(part)
            continue
        if Path(nombre).suffix.lower() in EXTENSIONES_OMITIDAS:
            continue
        es_inline = disposicion == "inline" or bool(content_id)
        if es_inline and ctype.startswith("image/") and len(contenido) < min_inline:
            logger.debug(f"Omitido logo de firma: {nombre} ({len(contenido)} bytes)")
            continue
        adjuntos.append((nombre, contenido))
    return texto_plano, html, inlines, adjuntos


def fecha_local_correo(msg: email.message.Message) -> datetime:
    valor = msg.get("Date")
    if valor:
        try:
            fecha = email.utils.parsedate_to_datetime(valor)
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=TZ_COLOMBIA)
            return fecha.astimezone(TZ_COLOMBIA)
        except (TypeError, ValueError):
            pass
    return datetime.now(TZ_COLOMBIA)


def id_mensaje(msg: email.message.Message) -> str:
    mid = (msg.get("Message-ID") or "").strip()
    if mid:
        return mid
    huella = f"{msg.get('Date', '')}|{msg.get('From', '')}|{msg.get('Subject', '')}"
    return "sha1:" + hashlib.sha1(huella.encode("utf-8", errors="replace")).hexdigest()


# ─── PDF del correo ──────────────────────────────────────────────────────────

_RUTAS_NAVEGADOR = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def buscar_navegador() -> str | None:
    """Edge/Chrome para imprimir el correo a PDF con fidelidad. None → reportlab."""
    configurado = os.environ.get("ORGANIZADOR_NAVEGADOR", "").strip()
    if configurado:
        return configurado if Path(configurado).exists() else None
    for ruta in _RUTAS_NAVEGADOR:
        if Path(ruta).exists():
            return ruta
    for nombre in ("msedge", "chrome", "chromium", "chromium-browser", "google-chrome"):
        encontrado = shutil.which(nombre)
        if encontrado:
            return encontrado
    return None


def armar_html_correo(
    meta: dict[str, str], html: str, texto: str, inlines: dict[str, tuple[str, bytes]]
) -> str:
    """HTML autocontenido con el encabezado tipo 'impresión de Gmail' + cuerpo."""
    cuerpo = html or f"<pre style='white-space:pre-wrap'>{_escape_xml(texto)}</pre>"
    for cid, (ctype, datos) in inlines.items():
        b64 = base64.b64encode(datos).decode("ascii")
        cuerpo = cuerpo.replace(f"cid:{cid}", f"data:{ctype};base64,{b64}")
    filas = "".join(
        f"<tr><td style='padding:2px 12px 2px 0;color:#555;white-space:nowrap'><b>{campo}</b></td>"
        f"<td style='padding:2px 0'>{_escape_xml(valor)}</td></tr>"
        for campo, valor in meta.items()
        if valor
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        '<body style="font-family:Arial,sans-serif;font-size:13px;margin:24px">'
        f"<h2 style='margin:0 0 8px'>{_escape_xml(meta.get('Asunto', ''))}</h2>"
        f"<table style='font-size:12px;border-collapse:collapse'>{filas}</table>"
        "<hr style='margin:12px 0;border:none;border-top:1px solid #999'>"
        f"{cuerpo}</body></html>"
    )


def generar_pdf_navegador(html_final: str, destino: Path, navegador: str) -> bool:
    with tempfile.TemporaryDirectory(prefix="correo_glosas_") as tmp:
        origen = Path(tmp) / "correo.html"
        origen.write_text(html_final, encoding="utf-8")
        cmd = [
            navegador,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={destino}",
            origen.as_uri(),
        ]
        try:
            proceso = subprocess.run(cmd, capture_output=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning(f"Navegador falló imprimiendo a PDF ({exc}); uso reportlab")
            return False
    if proceso.returncode != 0 or not destino.exists() or destino.stat().st_size == 0:
        logger.warning("Navegador no produjo el PDF; uso reportlab")
        destino.unlink(missing_ok=True)
        return False
    return True


def generar_pdf_reportlab(meta: dict[str, str], texto: str, destino: Path) -> None:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        sys.stderr.write(
            "ERROR: para generar el PDF del correo se necesita reportlab.\n"
            "Instálalo con: pip install reportlab\n"
            "(o ejecuta con --sin-pdf-correo para guardar solo adjuntos)\n"
        )
        sys.exit(2)

    estilos = getSampleStyleSheet()
    # wordWrap CJK: corta también palabras larguísimas (URLs) sin reventar el layout
    normal = ParagraphStyle(
        "cuerpo", parent=estilos["Normal"], fontSize=9.5, leading=13, wordWrap="CJK"
    )
    encabezado = ParagraphStyle("meta", parent=normal, textColor="#444444")
    doc = SimpleDocTemplate(
        str(destino),
        pagesize=letter,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=meta.get("Asunto", ""),
    )
    elementos = [Paragraph(_escape_xml(meta.get("Asunto", "")), estilos["Heading2"])]
    for campo, valor in meta.items():
        if valor and campo != "Asunto":
            elementos.append(Paragraph(f"<b>{campo}:</b> {_escape_xml(valor)}", encabezado))
    elementos.append(Spacer(1, 8))
    elementos.append(HRFlowable(width="100%", color="#888888"))
    elementos.append(Spacer(1, 8))
    for parrafo in texto.split("\n"):
        elementos.append(Paragraph(_escape_xml(parrafo) or "&nbsp;", normal))
    doc.build(elementos)


def generar_pdf_correo(
    meta: dict[str, str],
    texto: str,
    html: str,
    inlines: dict[str, tuple[str, bytes]],
    destino: Path,
    navegador: str | None,
) -> str:
    """Genera el PDF del correo. Devuelve el motor usado ('navegador'/'reportlab')."""
    if navegador and (html or texto):
        html_final = armar_html_correo(meta, html, texto, inlines)
        if generar_pdf_navegador(html_final, destino, navegador):
            return "navegador"
    cuerpo = texto or extraer_texto_html(html) or "(correo sin cuerpo de texto)"
    generar_pdf_reportlab(meta, cuerpo, destino)
    return "reportlab"


# ─── Rutas de destino y estado ───────────────────────────────────────────────


def construir_carpeta_destino(
    base: Path, fecha: datetime, categoria: str, entidad: str, config: dict
) -> Path:
    plantilla = config["plantillas"].get("carpeta_entidad", "{entidad}")
    carpeta_entidad = sanitizar(plantilla.format(entidad=entidad))
    return (
        base
        / f"{fecha.year}"
        / f"{fecha.month:02d} {MESES_ES[fecha.month - 1]}"
        / f"{fecha.day:02d}"
        / sanitizar(categoria)
        / carpeta_entidad
    )


def nombre_disponible(carpeta: Path, nombre: str) -> Path:
    """Nunca sobreescribir: si ya existe, agrega ' (2)', ' (3)', ..."""
    candidato = carpeta / nombre
    if not candidato.exists():
        return candidato
    tallo, extension = Path(nombre).stem, Path(nombre).suffix
    numero = 2
    while (carpeta / f"{tallo} ({numero}){extension}").exists():
        numero += 1
    return carpeta / f"{tallo} ({numero}){extension}"


def nombre_pdf_correo(
    categoria: str, entidad: str, asunto: str, consecutivo_fn, config: dict
) -> str:
    """Nombre del PDF del correo según plantilla por categoría.

    consecutivo_fn se invoca SOLO si la plantilla usa {consecutivo}, para no
    gastar numeración cuando no hace falta.
    """
    plantillas = config["plantillas"]["pdf_correo"]
    plantilla = plantillas.get(categoria, plantillas.get("*", "{entidad} {consecutivo} OK"))
    valores = {
        "entidad": entidad,
        "asunto": _acotar(sanitizar(asunto), 80),
        "radicado": extraer_radicado(asunto),
        "consecutivo": consecutivo_fn() if "{consecutivo}" in plantilla else "",
    }
    nombre = sanitizar(plantilla.format(**valores))
    return _acotar(nombre, 120) + ".pdf"


class Estado:
    """Estado persistente: Message-ID procesados + consecutivos por día/entidad."""

    def __init__(self, ruta: Path | None, datos: dict | None = None) -> None:
        self.ruta = ruta
        self.datos = datos or {"procesados": {}, "consecutivos": {}}

    @classmethod
    def cargar(cls, ruta: Path) -> Estado:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("estado no es un objeto")
            datos.setdefault("procesados", {})
            datos.setdefault("consecutivos", {})
            return cls(ruta, datos)
        except FileNotFoundError:
            return cls(ruta)
        except (json.JSONDecodeError, ValueError):
            respaldo = ruta.with_suffix(".corrupto.json")
            shutil.copy2(ruta, respaldo)
            logger.warning(
                f"Estado corrupto; respaldado en {respaldo}. OJO: se pierde la "
                "deduplicación previa, puede archivar duplicados con ' (2)'."
            )
            return cls(ruta)

    def ya_procesado(self, mid: str) -> bool:
        return mid in self.datos["procesados"]

    def marcar(self, mid: str) -> None:
        self.datos["procesados"][mid] = datetime.now(TZ_COLOMBIA).isoformat(timespec="seconds")

    def siguiente_consecutivo(self, fecha: datetime, entidad: str) -> int:
        clave = f"{fecha:%Y-%m-%d}|{_normalizar(entidad)}"
        numero = int(self.datos["consecutivos"].get(clave, 0)) + 1
        self.datos["consecutivos"][clave] = numero
        return numero

    def depurar(self, dias: int = 180) -> None:
        limite = (datetime.now(TZ_COLOMBIA) - timedelta(days=dias)).isoformat()
        procesados = self.datos["procesados"]
        for mid in [m for m, cuando in procesados.items() if cuando < limite]:
            del procesados[mid]

    def guardar(self) -> None:
        if self.ruta is None:
            return
        temporal = self.ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(self.datos, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporal, self.ruta)


CAMPOS_REGISTRO = [
    "fecha_proceso",
    "fecha_correo",
    "remitente",
    "asunto",
    "categoria",
    "entidad",
    "estado",
    "carpeta",
    "pdf_correo",
    "archivos",
    "motivo",
    "detalle",
    "mensaje_id",
]


def registrar_fila(control: Path, fila: dict) -> None:
    """Agrega la fila al registro mensual (CSV que abre directo en Excel)."""
    ahora = datetime.now(TZ_COLOMBIA)
    ruta = control / f"registro_{ahora:%Y-%m}.csv"
    nuevo = not ruta.exists()
    # BOM solo al crear el archivo; en append el códec utf-8-sig lo duplicaría
    with ruta.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CAMPOS_REGISTRO)
        if nuevo:
            writer.writeheader()
        writer.writerow({k: fila.get(k, "") for k in CAMPOS_REGISTRO})


# ─── IMAP ────────────────────────────────────────────────────────────────────


def cargar_credenciales() -> tuple[str, str, str]:
    host = os.environ.get("GLOSAS_IMAP_HOST", "").strip() or "imap.gmail.com"
    user = os.environ.get("GLOSAS_IMAP_USER", "").strip() or os.environ.get("IMAP_USER", "").strip()
    password = (
        os.environ.get("GLOSAS_IMAP_PASSWORD", "").strip()
        or os.environ.get("IMAP_PASSWORD", "").strip()
    )
    if not user or not password:
        sys.stderr.write(
            "ERROR: faltan credenciales IMAP. Configúralas con:\n"
            "    setx GLOSAS_IMAP_USER glosasydevoluciones@hus.gov.co\n"
            "    setx GLOSAS_IMAP_PASSWORD <contraseña de aplicación de 16 letras>\n"
            "Después cierra y reabre la consola.\n"
            "La contraseña de aplicación se crea en https://myaccount.google.com/apppasswords\n"
        )
        sys.exit(2)
    return host, user, password


def conectar_imap(host: str, user: str, password: str, carpeta: str) -> imaplib.IMAP4_SSL:
    try:
        conexion = imaplib.IMAP4_SSL(host)
        conexion.login(user, password)
    except imaplib.IMAP4.error as exc:
        sys.stderr.write(
            f"ERROR: login IMAP rechazado para {user}: {exc}\n"
            "Verifica que la verificación en dos pasos esté activa y que la\n"
            "contraseña sea una CONTRASEÑA DE APLICACIÓN (no la clave normal).\n"
        )
        sys.exit(2)
    typ, _ = conexion.select(f'"{carpeta}"')
    if typ != "OK":
        sys.stderr.write(f"ERROR: no pude abrir la carpeta IMAP '{carpeta}'\n")
        sys.exit(2)
    return conexion


def buscar_uids(conexion: imaplib.IMAP4_SSL, desde: datetime) -> list[bytes]:
    criterio = f"{desde.day:02d}-{MESES_IMAP[desde.month - 1]}-{desde.year}"
    typ, data = conexion.uid("SEARCH", None, "SINCE", criterio)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def obtener_mensaje(conexion: imaplib.IMAP4_SSL, uid: bytes) -> email.message.Message | None:
    # BODY.PEEK[]: no marca el correo como leído (bandeja compartida con humanos)
    typ, data = conexion.uid("FETCH", uid, "(BODY.PEEK[])")
    if typ != "OK" or not data:
        return None
    for parte in data:
        if isinstance(parte, tuple) and len(parte) >= 2 and isinstance(parte[1], bytes):
            return email.message_from_bytes(parte[1])
    return None


def etiquetar_procesado(conexion: imaplib.IMAP4_SSL, uid: bytes, etiqueta: str) -> None:
    """Etiqueta Gmail visual para los humanos; la dedup real es el archivo de estado."""
    try:
        typ, _ = conexion.uid("STORE", uid, "+X-GM-LABELS", f'("{etiqueta}")')
        if typ != "OK":
            logger.warning(f"No pude etiquetar UID {uid.decode()} con '{etiqueta}'")
    except imaplib.IMAP4.error as exc:
        logger.warning(f"El servidor no aceptó la etiqueta (¿no es Gmail?): {exc}")


# ─── Procesamiento de un correo ──────────────────────────────────────────────


def procesar_mensaje(
    msg: email.message.Message,
    *,
    base: Path,
    config: dict,
    estado: Estado,
    dry_run: bool,
    sin_pdf_correo: bool,
    navegador: str | None,
) -> dict:
    asunto = decodificar_encabezado(msg.get("Subject")) or "(sin asunto)"
    remitente = decodificar_encabezado(msg.get("From"))
    fecha = fecha_local_correo(msg)
    fila = {
        "fecha_proceso": datetime.now(TZ_COLOMBIA).isoformat(timespec="seconds"),
        "fecha_correo": fecha.isoformat(timespec="minutes"),
        "remitente": remitente,
        "asunto": asunto,
        "mensaje_id": id_mensaje(msg),
    }

    if debe_ignorarse(asunto, config):
        fila.update(estado="IGNORADO", motivo="asunto en lista de ignorados")
        return fila

    texto, html, inlines, adjuntos = extraer_partes(msg, config)
    nombres_adjuntos = [nombre for nombre, _ in adjuntos]
    categoria, motivo = clasificar_categoria(asunto, nombres_adjuntos, config)
    entidad, identificada = detectar_entidad(remitente, asunto, nombres_adjuntos, config)
    if not identificada:
        motivo += "; entidad por dominio del remitente"

    carpeta = construir_carpeta_destino(base, fecha, categoria, entidad, config)
    fila.update(categoria=categoria, entidad=entidad, motivo=motivo, carpeta=str(carpeta))

    nombre_pdf = ""
    if not sin_pdf_correo:
        nombre_pdf = nombre_pdf_correo(
            categoria,
            entidad,
            asunto,
            lambda: estado.siguiente_consecutivo(fecha, entidad),
            config,
        )

    if dry_run:
        archivos = ([nombre_pdf] if nombre_pdf else []) + [sanitizar(n) for n in nombres_adjuntos]
        fila.update(estado="DRY_RUN", archivos=" | ".join(archivos), pdf_correo=nombre_pdf)
        return fila

    carpeta.mkdir(parents=True, exist_ok=True)
    guardados: list[str] = []
    if nombre_pdf:
        destino_pdf = nombre_disponible(carpeta, nombre_pdf)
        meta = {
            "Asunto": asunto,
            "De": remitente,
            "Para": decodificar_encabezado(msg.get("To")),
            "CC": decodificar_encabezado(msg.get("Cc")),
            "Fecha": f"{fecha:%d/%m/%Y %H:%M} (hora Colombia)",
        }
        motor = generar_pdf_correo(meta, texto, html, inlines, destino_pdf, navegador)
        fila["pdf_correo"] = f"{destino_pdf.name} [{motor}]"
        guardados.append(destino_pdf.name)
    for nombre, contenido in adjuntos:
        destino = nombre_disponible(carpeta, _acotar(sanitizar(nombre), 120))
        destino.write_bytes(contenido)
        guardados.append(destino.name)

    estado_fila = "REVISAR" if categoria == config["categoria_revision"] else "ARCHIVADO"
    fila.update(estado=estado_fila, archivos=" | ".join(guardados))
    return fila


# ─── Orquestación ────────────────────────────────────────────────────────────


def _parsear_fecha(valor: str) -> datetime:
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(valor, formato).replace(tzinfo=TZ_COLOMBIA)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"fecha inválida: {valor} (usa AAAA-MM-DD o DD/MM/AAAA)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=Path(DEFAULT_BASE),
        help=f"Carpeta raíz de glosas escaneadas (default: {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--control",
        type=Path,
        default=None,
        help=f"Carpeta de estado/registro/logs (default: <base>\\{DEFAULT_CONTROL})",
    )
    parser.add_argument("--config", type=Path, default=None, help="JSON de entidades/categorías")
    parser.add_argument(
        "--carpeta-imap",
        default=DEFAULT_CARPETA_IMAP,
        help=f"Carpeta IMAP a leer (default: {DEFAULT_CARPETA_IMAP})",
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=DEFAULT_DIAS,
        help=f"Revisar correos de los últimos N días (default: {DEFAULT_DIAS})",
    )
    parser.add_argument(
        "--desde",
        type=_parsear_fecha,
        default=None,
        help="Revisar desde esta fecha (AAAA-MM-DD); reemplaza a --dias",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX,
        help=f"Máximo de correos a procesar por corrida (default: {DEFAULT_MAX})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="No escribe ni etiqueta nada; solo muestra"
    )
    parser.add_argument(
        "--no-marcar", action="store_true", help="No poner la etiqueta de Gmail al procesar"
    )
    parser.add_argument(
        "--sin-pdf-correo", action="store_true", help="No generar el PDF del correo"
    )
    parser.add_argument(
        "--log", type=Path, default=None, help="Archivo de log (default: en control)"
    )
    args = parser.parse_args()

    control: Path = args.control or (args.base / DEFAULT_CONTROL)
    log_file = args.log
    if log_file is None and not args.dry_run:
        log_file = control / "organizador.log"
    try:
        if not args.dry_run:
            control.mkdir(parents=True, exist_ok=True)
        setup_logging(log_file)
    except OSError as exc:
        sys.stderr.write(
            f"ERROR: no pude crear la carpeta de control {control}: {exc}\n"
            "¿Está mapeada la unidad Z:? Puedes probar con --base C:\\pruebas --dry-run\n"
        )
        return 2

    config = cargar_config(args.config)
    navegador = None if args.sin_pdf_correo else buscar_navegador()
    if not args.sin_pdf_correo and navegador is None:
        # sin navegador, reportlab es obligatorio: fallar temprano y claro
        try:
            import reportlab  # noqa: F401
        except ImportError:
            sys.stderr.write(
                "ERROR: no hay Edge/Chrome ni reportlab para generar el PDF del correo.\n"
                "Instala reportlab con: pip install reportlab\n"
            )
            return 2

    ruta_estado = control / "estado_organizador.json"
    if args.dry_run:
        try:
            estado = Estado.cargar(ruta_estado)
        except OSError:
            estado = Estado(None)
        estado.ruta = None  # jamás persistir en simulacro
    else:
        estado = Estado.cargar(ruta_estado)

    host, user, password = cargar_credenciales()
    desde = args.desde or (datetime.now(TZ_COLOMBIA) - timedelta(days=args.dias))
    logger.info(f"Conectando a {host} como {user} (carpeta {args.carpeta_imap})")
    conexion = conectar_imap(host, user, password, args.carpeta_imap)

    try:
        uids = buscar_uids(conexion, desde)
        logger.info(f"Correos desde {desde:%d/%m/%Y}: {len(uids)} en la bandeja")
        resumen: dict[str, int] = {}
        errores = 0
        procesados = 0
        for uid in uids:
            if procesados >= args.max:
                logger.warning(f"Alcanzado --max {args.max}; quedan correos pendientes")
                break
            msg = obtener_mensaje(conexion, uid)
            if msg is None:
                logger.warning(f"UID {uid.decode()}: no pude descargar el mensaje")
                errores += 1
                continue
            mid = id_mensaje(msg)
            if estado.ya_procesado(mid):
                resumen["YA_PROCESADO"] = resumen.get("YA_PROCESADO", 0) + 1
                continue
            procesados += 1
            try:
                fila = procesar_mensaje(
                    msg,
                    base=args.base,
                    config=config,
                    estado=estado,
                    dry_run=args.dry_run,
                    sin_pdf_correo=args.sin_pdf_correo,
                    navegador=navegador,
                )
            except Exception as exc:  # correo con errores no debe frenar el lote
                logger.exception(f"UID {uid.decode()}: error procesando")
                fila = {
                    "fecha_proceso": datetime.now(TZ_COLOMBIA).isoformat(timespec="seconds"),
                    "asunto": decodificar_encabezado(msg.get("Subject")),
                    "remitente": decodificar_encabezado(msg.get("From")),
                    "mensaje_id": mid,
                    "estado": "ERROR",
                    "detalle": str(exc),
                }
            estado_fila = fila.get("estado", "ERROR")
            resumen[estado_fila] = resumen.get(estado_fila, 0) + 1
            logger.info(
                f"[{estado_fila}] {fila.get('categoria', '-')} / {fila.get('entidad', '-')} "
                f"<- {_acotar(fila.get('asunto', ''), 70)}"
            )
            if estado_fila == "ERROR":
                errores += 1
                continue  # sin marcar: se reintenta en la próxima corrida
            if not args.dry_run:
                estado.marcar(mid)
                estado.depurar()
                estado.guardar()
                registrar_fila(control, fila)
                if not args.no_marcar:
                    etiquetar_procesado(conexion, uid, config["etiqueta_gmail"])
    finally:
        with contextlib.suppress(OSError, imaplib.IMAP4.error):
            conexion.logout()

    logger.info("=" * 60)
    logger.info("RESUMEN FINAL")
    for estado_fila in sorted(resumen):
        logger.info(f"  {estado_fila}: {resumen[estado_fila]}")
    if not args.dry_run:
        logger.info(
            f"  Registro CSV: {control / f'registro_{datetime.now(TZ_COLOMBIA):%Y-%m}.csv'}"
        )
    logger.info("=" * 60)
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
