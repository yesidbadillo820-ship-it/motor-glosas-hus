"""organizar_correos_glosas.py — Archiva correos de glosas/devoluciones en el servidor Z:.

Lee la bandeja institucional (glosasydevoluciones@hus.gov.co) por IMAP, clasifica
cada correo en INICIAL / RATIFICADA / DEVOLUCIONES / CONCILIACIONES (o 0-REVISAR
si no hay certeza), detecta la entidad pagadora (DISPENSARIO/AUDITOOL, AXA,
SEGUROS BOLIVAR, SALUD MIA, ...) y guarda en la estructura del servidor de glosas:

    <base>\\<AÑO>\\<MM MES>\\<DD>\\<CATEGORÍA>\\<ENTIDAD OK>\\
        ├── <ENTIDAD> <h.mm> OK.pdf   (el correo impreso a PDF; h.mm = hora de llegada,
        │                              como el archivo manual: "AXA 7.21 OK.pdf")
        └── <adjuntos>                (renombrados con la misma convención)

Si la carpeta del día/categoría/entidad ya existe con marcas manuales
("01 OK SOLO NUEVA", "DEVOLUCIONES OK", "DISPENSARIO SOFIA OK", "07.JULIO"),
se REUTILIZA esa carpeta en vez de crear una duplicada.

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
        {"nombre": "RATIFICADA", "patrones": ["RATIFICA"]},
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
            "remitente": ["SEGUROSBOLIVAR", "@BOLIVAR"],
            "asunto": ["SEGUROS\\s+BOLIVAR"],
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
            "*": "{entidad} {hora} OK",
        },
    },
    # Los adjuntos toman el mismo nombre que el PDF del correo (convención del
    # archivo manual: "AXA 7.21 OK.pdf" + "AXA 7.21 OK (2).pdf"). Con false
    # conservan su nombre original.
    "renombrar_adjuntos": True,
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


def _decodificar_bytes(texto: bytes, charset: str | None) -> str:
    """decode() lanza LookupError con charsets inexistentes ('unknown-8bit',
    'iso-8859-8-i') aunque se pase errors='replace': probar con fallbacks."""
    for codec, errores in ((charset or "utf-8", "replace"), ("utf-8", "strict")):
        try:
            return texto.decode(codec, errores)
        except (LookupError, UnicodeDecodeError):
            continue
    return texto.decode("latin-1", errors="replace")


def decodificar_encabezado(valor: str | None) -> str:
    """Decodifica encabezados MIME (=?UTF-8?Q?...?=) a texto plano.

    Nunca lanza: un charset corrupto en un solo correo no puede tumbar la
    corrida programada (quedaría en bucle venenoso cada 15 minutos).
    """
    if not valor:
        return ""
    partes: list[str] = []
    try:
        fragmentos = email.header.decode_header(valor)
    except Exception:
        return re.sub(r"\s+", " ", str(valor)).strip()
    for texto, charset in fragmentos:
        if isinstance(texto, bytes):
            partes.append(_decodificar_bytes(texto, charset))
        else:
            partes.append(texto)
    return re.sub(r"\s+", " ", "".join(partes)).strip()


def cargar_config(ruta: Path | None) -> dict:
    """Config por defecto, con las claves presentes en el JSON del usuario encima.

    'plantillas' se fusiona clave por clave (un config parcial no puede dejar
    al script sin plantilla); 'entidades_extra' se antepone a las entidades de
    fábrica sin reemplazarlas; el resto de claves de primer nivel reemplazan.
    """
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
    plantillas_propias = propia.pop("plantillas", None)
    entidades_extra = propia.pop("entidades_extra", None)
    config.update(propia)
    if isinstance(plantillas_propias, dict):
        pdf_propio = plantillas_propias.pop("pdf_correo", None)
        config["plantillas"].update(plantillas_propias)
        if isinstance(pdf_propio, dict):
            config["plantillas"]["pdf_correo"].update(pdf_propio)
    if isinstance(entidades_extra, list):
        config["entidades"] = entidades_extra + config["entidades"]
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
    return _decodificar_bytes(payload, part.get_content_charset())


def _extension_por_mime(ctype: str) -> str:
    import mimetypes

    return mimetypes.guess_extension(ctype or "") or ".bin"


def extraer_partes(
    msg: email.message.Message, config: dict
) -> tuple[str, str, dict[str, tuple[str, bytes]], list[tuple[str, bytes]]]:
    """Devuelve (texto_plano, html, imagenes_inline_por_cid, adjuntos).

    - imagenes_inline_por_cid: para incrustar en el PDF del correo (data URI).
    - adjuntos: [(nombre, contenido)] a guardar en la carpeta destino. Se omiten
      logos de firma (imágenes inline pequeñas) y firmas S/MIME. Los adjuntos
      sin nombre reciben uno generado (nunca se descartan). Los correos
      reenviados como adjunto (message/rfc822) se guardan como .eml y sus
      partes internas no contaminan el cuerpo del correo principal.
    """
    min_inline = int(config.get("min_bytes_imagen_inline", 15000))
    texto_plano, html = "", ""
    inlines: dict[str, tuple[str, bytes]] = {}
    adjuntos: list[tuple[str, bytes]] = []
    sin_nombre = 0

    # correos reenviados como adjunto: serializarlos y excluir sus sub-partes
    partes_anidadas: set[int] = set()
    for part in msg.walk():
        if part.get_content_type() == "message/rfc822" and id(part) not in partes_anidadas:
            for sub in part.walk():
                if sub is not part:
                    partes_anidadas.add(id(sub))
            anidado = part.get_payload(0) if part.get_payload() else None
            if anidado is not None:
                asunto_interno = decodificar_encabezado(anidado.get("Subject")) or "correo adjunto"
                try:
                    crudo = anidado.as_bytes()
                except Exception:
                    crudo = b""
                if crudo:
                    adjuntos.append((f"{asunto_interno}.eml", crudo))

    for part in msg.walk():
        if id(part) in partes_anidadas or part.get_content_maintype() == "multipart":
            continue
        ctype = part.get_content_type()
        if ctype == "message/rfc822":
            continue  # ya serializado arriba
        disposicion = (part.get_content_disposition() or "").lower()
        nombre = decodificar_encabezado(part.get_filename())
        contenido = part.get_payload(decode=True) or b""
        content_id = (part.get("Content-ID") or "").strip("<> \t")
        if content_id and ctype.startswith("image/"):
            inlines[content_id] = (ctype, contenido)
        if not nombre:
            if ctype == "text/plain" and disposicion != "attachment" and not texto_plano:
                texto_plano = _texto_de_parte(part)
                continue
            if ctype == "text/html" and disposicion != "attachment" and not html:
                html = _texto_de_parte(part)
                continue
            if ctype.startswith("text/") or not contenido:
                continue
            # adjunto sin nombre: generarle uno en vez de perder el documento
            sin_nombre += 1
            nombre = f"adjunto sin nombre {sin_nombre}{_extension_por_mime(ctype)}"
        if Path(nombre).suffix.lower() in EXTENSIONES_OMITIDAS:
            continue
        es_inline = disposicion == "inline" or bool(content_id)
        if es_inline and ctype.startswith("image/") and len(contenido) < min_inline:
            logger.debug(f"Omitido logo de firma: {nombre} ({len(contenido)} bytes)")
            continue
        adjuntos.append((nombre, contenido))
    return texto_plano, html, inlines, adjuntos


def fecha_local_correo(msg: email.message.Message) -> datetime:
    """Fecha de llegada en hora Colombia, acotada a un rango sano: un remitente
    con el reloj dañado no puede archivar en '2003' ni en el futuro."""
    ahora = datetime.now(TZ_COLOMBIA)
    valor = msg.get("Date")
    if valor:
        try:
            fecha = email.utils.parsedate_to_datetime(valor)
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=TZ_COLOMBIA)
            fecha = fecha.astimezone(TZ_COLOMBIA)
            if fecha.year >= 2020 and fecha <= ahora + timedelta(days=2):
                return fecha
            logger.warning(f"Fecha de correo fuera de rango ({fecha:%Y-%m-%d}); uso hoy")
        except (TypeError, ValueError, OverflowError):
            pass
    return ahora


def id_mensaje(msg: email.message.Message) -> str:
    mid = (msg.get("Message-ID") or "").strip()
    if mid:
        return mid
    # solo campos presentes también en el fetch de encabezados, para que el
    # id del pre-chequeo coincida con el del mensaje completo
    huella = "|".join(str(msg.get(campo, "")) for campo in ("Date", "From", "To", "Subject"))
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
            "--disable-extensions",
            # proxy inalcanzable: el HTML del remitente no puede cargar recursos
            # remotos ni servir de beacon/SSRF; las imágenes van como data: URI
            "--proxy-server=127.0.0.1:9",
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


def _clave_carpeta(nombre: str) -> str:
    """Normaliza un nombre de carpeta para compararlo: '07.JULIO' == '07 JULIO'."""
    texto = _normalizar(nombre).replace(".", " ")
    return re.sub(r"\s+", " ", texto).strip()


def carpeta_equivalente(padre: Path, objetivo: str, nombre_nuevo: str | None = None) -> Path:
    """Reutiliza una carpeta existente aunque tenga marcas manuales.

    El personal agrega sufijos a mano ('01 OK SOLO NUEVA', 'DEVOLUCIONES OK',
    'DISPENSARIO SOFIA OK', '07.JULIO'): si en `padre` ya hay una carpeta cuyo
    nombre normalizado es igual al objetivo, empieza por 'objetivo ' o es el
    plural 'objetivoS', se usa esa en vez de crear una duplicada. Si no hay,
    devuelve padre/nombre_nuevo (o padre/objetivo).
    """
    clave = _clave_carpeta(objetivo)
    try:
        existentes = [d for d in padre.iterdir() if d.is_dir()]
    except OSError:
        existentes = []
    candidatas = []
    for carpeta in existentes:
        nombre = _clave_carpeta(carpeta.name)
        if nombre == clave or nombre == clave + "S" or nombre.startswith(clave + " "):
            candidatas.append(carpeta)
    if candidatas:
        # la de nombre más corto es la más cercana al objetivo
        return min(candidatas, key=lambda c: len(c.name))
    return padre / sanitizar(nombre_nuevo or objetivo)


def construir_carpeta_destino(
    base: Path, fecha: datetime, categoria: str, entidad: str, config: dict
) -> Path:
    plantilla = config["plantillas"].get("carpeta_entidad", "{entidad}")
    anio = base / f"{fecha.year}"
    mes = carpeta_equivalente(anio, f"{fecha.month:02d} {MESES_ES[fecha.month - 1]}")
    dia = carpeta_equivalente(mes, f"{fecha.day:02d}")
    cat = carpeta_equivalente(dia, categoria)
    # la entidad se busca por su nombre pelado ('DISPENSARIO' encuentra
    # 'DISPENSARIO SOFIA OK'); si no existe se crea con la plantilla (+' OK')
    try:
        nombre_nuevo = plantilla.format(entidad=entidad)
    except (ValueError, KeyError, IndexError):
        nombre_nuevo = f"{entidad} OK"
    return carpeta_equivalente(cat, entidad, nombre_nuevo)


_NOMBRES_RESERVADOS = {"CON", "PRN", "AUX", "NUL"} | {
    f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)
}
MAX_RUTA_WINDOWS = 255  # margen bajo el MAX_PATH de 260 (LongPathsEnabled suele estar apagado)


def nombre_archivo_seguro(nombre: str, max_tallo: int = 100) -> str:
    """Sanitiza conservando la extensión y evitando nombres reservados (CON, PRN...)."""
    limpio = sanitizar(nombre) or "sin nombre"
    tallo, extension = Path(limpio).stem, Path(limpio).suffix[:10]
    tallo = _acotar(tallo, max_tallo).rstrip(". ") or "sin nombre"
    if tallo.upper() in _NOMBRES_RESERVADOS:
        tallo = f"_{tallo}"
    return f"{tallo}{extension}"


def nombre_disponible(carpeta: Path, nombre: str) -> Path:
    """Nunca sobreescribir: si ya existe, agrega ' (2)', ' (3)', ...
    Recorta el nombre si la ruta completa supera el MAX_PATH de Windows."""
    extension = Path(nombre).suffix
    # +6 de margen para el sufijo ' (99)'
    exceso = len(str(carpeta / nombre)) + 6 - MAX_RUTA_WINDOWS
    if exceso > 0:
        tallo = Path(nombre).stem
        tallo = _acotar(tallo, max(8, len(tallo) - exceso)).rstrip(". ")
        nombre = f"{tallo}{extension}"
        logger.warning(f"Ruta muy larga: nombre recortado a '{nombre}'")
    candidato = carpeta / nombre
    if not candidato.exists():
        return candidato
    tallo = Path(nombre).stem
    numero = 2
    while (carpeta / f"{tallo} ({numero}){extension}").exists():
        numero += 1
    return carpeta / f"{tallo} ({numero}){extension}"


def hora_correo(fecha: datetime) -> str:
    """Hora de llegada en el formato del archivo manual: 7.21, 1.30 (12 horas)."""
    hora_12 = fecha.hour % 12 or 12
    return f"{hora_12}.{fecha.minute:02d}"


def nombre_pdf_correo(
    categoria: str, entidad: str, asunto: str, fecha: datetime, consecutivo_fn, config: dict
) -> str:
    """Nombre del PDF del correo según plantilla por categoría.

    Variables: {entidad}, {hora} (llegada, ej. 7.21), {asunto}, {radicado},
    {consecutivo} (contador por día/entidad; solo se gasta si la plantilla lo usa).
    """
    plantillas = config.get("plantillas", {}).get("pdf_correo", {})
    plantilla = plantillas.get(categoria) or plantillas.get("*") or "{entidad} {hora} OK"
    valores = {
        "entidad": entidad,
        "hora": hora_correo(fecha),
        "asunto": _acotar(sanitizar(asunto), 80),
        "radicado": extraer_radicado(asunto),
        "consecutivo": consecutivo_fn() if "{consecutivo}" in plantilla else "",
    }

    class _SinFaltantes(dict):
        def __missing__(self, clave: str) -> str:
            return ""

    try:
        nombre = plantilla.format_map(_SinFaltantes(valores))
    except (ValueError, KeyError, IndexError):
        # plantilla mal escrita en el config: nunca frenar el archivado
        logger.warning(f"Plantilla inválida '{plantilla}'; uso la de fábrica")
        nombre = "{entidad} {hora} OK".format_map(_SinFaltantes(valores))
    return nombre_archivo_seguro(nombre, max_tallo=120) + ".pdf"


MAX_REINTENTOS_CORREO = 3


class Estado:
    """Estado persistente: Message-ID procesados, reintentos fallidos y
    consecutivos por día/entidad."""

    def __init__(self, ruta: Path | None, datos: dict | None = None) -> None:
        self.ruta = ruta
        self.datos = datos or {}
        self.datos.setdefault("procesados", {})
        self.datos.setdefault("consecutivos", {})
        self.datos.setdefault("fallidos", {})

    @classmethod
    def cargar(cls, ruta: Path, respaldar_corrupto: bool = True) -> Estado:
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("estado no es un objeto")
            return cls(ruta, datos)
        except FileNotFoundError:
            return cls(ruta)
        except (json.JSONDecodeError, ValueError):
            if respaldar_corrupto:
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
        self.datos["fallidos"].pop(mid, None)

    def registrar_fallo(self, mid: str) -> int:
        """Cuenta un intento fallido; devuelve el total acumulado."""
        total = int(self.datos["fallidos"].get(mid, 0)) + 1
        self.datos["fallidos"][mid] = total
        return total

    def fallos(self, mid: str) -> int:
        return int(self.datos["fallidos"].get(mid, 0))

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
        # los consecutivos llevan la fecha en la clave: podar los viejos también
        limite_dia = limite[:10]
        consecutivos = self.datos["consecutivos"]
        for clave in [c for c in consecutivos if c[:10] < limite_dia]:
            del consecutivos[clave]

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
    candidatas = (
        control / f"registro_{ahora:%Y-%m}.csv",
        # si el registro está abierto en Excel (PermissionError), la fila cae
        # al archivo pendiente en vez de perderse o tumbar la corrida
        control / f"registro_{ahora:%Y-%m}_pendiente.csv",
    )
    for ruta in candidatas:
        nuevo = not ruta.exists()
        try:
            # BOM solo al crear el archivo; en append el códec utf-8-sig lo duplicaría
            with ruta.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=CAMPOS_REGISTRO)
                if nuevo:
                    writer.writeheader()
                writer.writerow({k: fila.get(k, "") for k in CAMPOS_REGISTRO})
            return
        except OSError as exc:
            logger.warning(f"No pude escribir en {ruta.name}: {exc}")
    logger.error("Fila de registro perdida (¿CSV abierto en Excel y disco lleno?)")


# ─── IMAP ────────────────────────────────────────────────────────────────────


def _codificar_carpeta_imap(carpeta: str) -> str:
    """Nombre de carpeta en UTF-7 modificado de IMAP (RFC 3501) si trae no-ASCII."""
    try:
        carpeta.encode("ascii")
        return carpeta
    except UnicodeEncodeError:
        codificada = carpeta.encode("utf-7").decode("ascii")
        return codificada.replace("+", "&").replace("/", ",")


def etiqueta_segura(etiqueta: str) -> str:
    """X-GM-LABELS viaja como literal ASCII entre comillas: sin tildes ni comillas."""
    plana = _quitar_diacriticos(etiqueta).replace('"', "").replace("\\", "")
    plana = re.sub(r"[^\x20-\x7e]", "", plana).strip()
    return re.sub(r"\s+", "-", plana) or "Archivado-Glosas"


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
        # timeout: un socket colgado (VPN caída, firewall) no puede congelar la
        # tarea programada para siempre
        conexion = imaplib.IMAP4_SSL(host, timeout=60)
        conexion.login(user, password)
    except imaplib.IMAP4.error as exc:
        sys.stderr.write(
            f"ERROR: login IMAP rechazado para {user}: {exc}\n"
            "Verifica que la verificación en dos pasos esté activa y que la\n"
            "contraseña sea una CONTRASEÑA DE APLICACIÓN (no la clave normal).\n"
        )
        sys.exit(2)
    except OSError as exc:
        sys.stderr.write(f"ERROR: no pude conectar a {host}: {exc}\n")
        sys.exit(2)
    typ, _ = conexion.select(f'"{_codificar_carpeta_imap(carpeta)}"')
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


def _mensaje_de_fetch(data) -> email.message.Message | None:
    for parte in data or []:
        if isinstance(parte, tuple) and len(parte) >= 2 and isinstance(parte[1], bytes):
            return email.message_from_bytes(parte[1])
    return None


def obtener_encabezados(conexion: imaplib.IMAP4_SSL, uid: bytes) -> email.message.Message | None:
    """Solo los encabezados que necesita la dedup: evita re-descargar cuerpos
    completos de toda la ventana en cada corrida (límite de ancho de banda
    IMAP de Gmail: ~2.5 GB/día)."""
    typ, data = conexion.uid(
        "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE FROM TO SUBJECT)])"
    )
    if typ != "OK":
        return None
    return _mensaje_de_fetch(data)


def obtener_mensaje(conexion: imaplib.IMAP4_SSL, uid: bytes) -> email.message.Message | None:
    # BODY.PEEK[]: no marca el correo como leído (bandeja compartida con humanos)
    typ, data = conexion.uid("FETCH", uid, "(BODY.PEEK[])")
    if typ != "OK":
        return None
    return _mensaje_de_fetch(data)


def etiquetar_procesado(conexion: imaplib.IMAP4_SSL, uid: bytes, etiqueta: str) -> None:
    """Etiqueta Gmail visual para los humanos; la dedup real es el archivo de estado."""
    try:
        typ, _ = conexion.uid("STORE", uid, "+X-GM-LABELS", f'("{etiqueta_segura(etiqueta)}")')
        if typ != "OK":
            logger.warning(f"No pude etiquetar UID {uid.decode()} con '{etiqueta}'")
    except (imaplib.IMAP4.error, UnicodeEncodeError) as exc:
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
            fecha,
            lambda: estado.siguiente_consecutivo(fecha, entidad),
            config,
        )

    def _nombre_adjunto(original: str) -> str:
        """Convención manual: el adjunto toma el nombre del correo, con su extensión."""
        if config.get("renombrar_adjuntos", True) and nombre_pdf:
            return Path(nombre_pdf).stem + Path(original).suffix.lower()
        return nombre_archivo_seguro(original, max_tallo=120)

    if dry_run:
        archivos = ([nombre_pdf] if nombre_pdf else []) + [
            f"{_nombre_adjunto(n)} <- {sanitizar(n)}" for n in nombres_adjuntos
        ]
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
        destino = nombre_disponible(carpeta, _nombre_adjunto(nombre))
        destino.write_bytes(contenido)
        guardados.append(f"{destino.name} <- {sanitizar(nombre)}")

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


LOCK_VIEJO_MINUTOS = 90  # un lock más viejo que esto se considera huérfano (crash previo)


def _adquirir_lock(ruta: Path) -> bool:
    try:
        antiguedad = datetime.now().timestamp() - ruta.stat().st_mtime
        if antiguedad > LOCK_VIEJO_MINUTOS * 60:
            logger.warning("Lock huérfano de una corrida caída; lo reemplazo")
            ruta.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    try:
        descriptor = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        return True
    except FileExistsError:
        return False
    except OSError as exc:
        logger.warning(f"No pude crear el lock ({exc}); continúo sin él")
        return True


def _liberar_lock(ruta: Path) -> None:
    with contextlib.suppress(OSError):
        ruta.unlink(missing_ok=True)


def _fila_error(mid: str, cab: email.message.Message, detalle: str, estado_fila: str) -> dict:
    return {
        "fecha_proceso": datetime.now(TZ_COLOMBIA).isoformat(timespec="seconds"),
        "asunto": decodificar_encabezado(cab.get("Subject")),
        "remitente": decodificar_encabezado(cab.get("From")),
        "mensaje_id": mid,
        "estado": estado_fila,
        "detalle": detalle,
    }


def _procesar_uid(
    conexion: imaplib.IMAP4_SSL,
    uid: bytes,
    estado: Estado,
    config: dict,
    args,
    navegador: str | None,
    control: Path,
    resumen: dict[str, int],
) -> dict | None:
    """Pipeline de un correo: dedup por encabezados → descarga → archivado →
    persistencia. Devuelve la fila (o None si se saltó sin procesar)."""

    def _contar(clave: str) -> None:
        resumen[clave] = resumen.get(clave, 0) + 1

    # 1. Solo encabezados para la dedup: no re-descargar cuerpos ya procesados
    cab = obtener_encabezados(conexion, uid)
    if cab is None:
        logger.warning(f"UID {uid.decode()}: no pude leer los encabezados")
        _contar("DESCARGA_FALLIDA")
        return {"estado": "ERROR"}
    mid = id_mensaje(cab)
    if estado.ya_procesado(mid):
        _contar("YA_PROCESADO")
        return None

    # 2. Correo venenoso: tras N intentos fallidos se descarta con rastro en el
    #    CSV, para que no bloquee ni duplique cada 15 minutos para siempre
    if not args.dry_run and estado.fallos(mid) >= MAX_REINTENTOS_CORREO:
        fila = _fila_error(
            mid, cab, f"descartado tras {MAX_REINTENTOS_CORREO} intentos", "ERROR_DESCARTADO"
        )
        logger.error(f"[ERROR_DESCARTADO] {_acotar(fila['asunto'], 70)} — revisar a mano")
        estado.marcar(mid)
        estado.guardar()
        registrar_fila(control, fila)
        _contar("ERROR_DESCARTADO")
        return fila

    # 3. Descarga completa y procesamiento
    msg = obtener_mensaje(conexion, uid)
    if msg is None:
        logger.warning(f"UID {uid.decode()}: no pude descargar el mensaje")
        _contar("DESCARGA_FALLIDA")
        return {"estado": "ERROR"}
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
        fila = _fila_error(mid, cab, str(exc), "ERROR")
        if not args.dry_run:
            intento = estado.registrar_fallo(mid)
            estado.guardar()
            registrar_fila(control, fila | {"detalle": f"{exc} (intento {intento})"})

    estado_fila = fila.get("estado", "ERROR")
    _contar(estado_fila)
    logger.info(
        f"[{estado_fila}] {fila.get('categoria', '-')} / {fila.get('entidad', '-')} "
        f"<- {_acotar(fila.get('asunto', ''), 70)}"
    )
    if estado_fila == "ERROR":
        return fila
    if not args.dry_run:
        estado.marcar(mid)
        estado.depurar()
        estado.guardar()
        registrar_fila(control, fila)
        if not args.no_marcar:
            etiquetar_procesado(conexion, uid, config["etiqueta_gmail"])
    return fila


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

    if not args.dry_run and not args.base.is_dir():
        # nunca crear silenciosamente un árbol Z:\... fantasma en el disco local
        sys.stderr.write(
            f"ERROR: la carpeta base no existe: {args.base}\n"
            "¿Está mapeada la unidad Z:? Para probar sin ella: --base C:\\pruebas --dry-run\n"
        )
        return 2

    control: Path = args.control or (args.base / DEFAULT_CONTROL)
    log_file = args.log
    if log_file is None and not args.dry_run:
        log_file = control / "organizador.log"
    try:
        if not args.dry_run:
            control.mkdir(parents=True, exist_ok=True)
        setup_logging(log_file)
    except OSError as exc:
        sys.stderr.write(f"ERROR: no pude crear la carpeta de control {control}: {exc}\n")
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

    # lock: la tarea de 15 min y una corrida manual no deben solaparse
    # (duplicarían archivos y corromperían estado/CSV)
    lock = None
    if not args.dry_run:
        lock = control / "organizador.lock"
        if not _adquirir_lock(lock):
            logger.info("Otra corrida está en curso; salgo sin hacer nada")
            return 0

    try:
        ruta_estado = control / "estado_organizador.json"
        if args.dry_run:
            try:
                estado = Estado.cargar(ruta_estado, respaldar_corrupto=False)
            except OSError:
                estado = Estado(None)
            estado.ruta = None  # jamás persistir en simulacro
        else:
            estado = Estado.cargar(ruta_estado)

        host, user, password = cargar_credenciales()
        desde = args.desde or (datetime.now(TZ_COLOMBIA) - timedelta(days=args.dias))
        logger.info(f"Conectando a {host} como {user} (carpeta {args.carpeta_imap})")
        conexion = conectar_imap(host, user, password, args.carpeta_imap)

        resumen: dict[str, int] = {}
        errores = 0
        procesados = 0
        try:
            uids = buscar_uids(conexion, desde)
            logger.info(f"Correos desde {desde:%d/%m/%Y}: {len(uids)} en la bandeja")
            for uid in uids:
                if procesados >= args.max:
                    logger.warning(f"Alcanzado --max {args.max}; quedan correos pendientes")
                    break
                try:
                    fila_o_none = _procesar_uid(
                        conexion, uid, estado, config, args, navegador, control, resumen
                    )
                except (imaplib.IMAP4.abort, OSError) as exc:
                    # conexión perdida a mitad de lote: lo hecho queda hecho,
                    # el resto se retoma en la próxima corrida
                    logger.error(f"Conexión IMAP perdida ({exc}); retomo en la próxima corrida")
                    resumen["CONEXION_PERDIDA"] = resumen.get("CONEXION_PERDIDA", 0) + 1
                    errores += 1
                    break
                if fila_o_none is None:
                    continue
                procesados += 1
                if fila_o_none.get("estado") == "ERROR":
                    errores += 1
        finally:
            with contextlib.suppress(OSError, imaplib.IMAP4.error):
                conexion.logout()
    finally:
        if lock is not None:
            _liberar_lock(lock)

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
