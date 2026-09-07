"""Lectura en cascada de la factura en PDF (soporte de radicación).

Saca del PDF los datos que el bot inyecta en la respuesta: nombre del
paciente, valor total de la factura y las filas de servicios. Tres intentos
en orden, y se queda con el primero que entregue texto útil:

  1. pdfplumber  — prioridad: conserva la estructura (extract_table y
                   extract_text con layout) de las facturas electrónicas.
  2. PyPDF2      — rescate rápido si pdfplumber falla o devuelve vacío.
  3. pytesseract — para PDF escaneados (imagen): rasteriza con PyMuPDF y
                   fuerza la lectura con OCR. Si Tesseract no está instalado
                   en el equipo, este intento se omite con aviso.

REGLA DE NO INVENCIÓN: lo que no se pueda leer queda en None. El bot solo
usa en la redacción los datos que de verdad salieron del PDF.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _dinero import a_entero  # noqa: E402  (el UNICO lector de pesos de tools/)

MIN_TEXTO_UTIL = 30  # caracteres alfanuméricos para considerar "leído"

RE_PACIENTE = [
    re.compile(r"(?:NOMBRE\s+DEL?\s+)?PACIENTE\s*[:\-]\s*([A-ZÑÁÉÍÓÚ ]{5,60})"),
    re.compile(r"NOMBRE\s*[:\-]\s*([A-ZÑÁÉÍÓÚ ]{5,60})"),
    re.compile(r"USUARIO\s*[:\-]\s*([A-ZÑÁÉÍÓÚ ]{5,60})"),
    re.compile(r"SE[ÑN]OR\(?E?S?\)?\s*[:\-]?\s*([A-ZÑÁÉÍÓÚ ]{5,60})"),
]
RE_TOTAL = [
    re.compile(
        r"(?:TOTAL\s+A\s+PAGAR|VALOR\s+TOTAL|TOTAL\s+FACTURA)\s*[:\-]?\s*\$?\s*([\d.,]{4,})"
    ),
    re.compile(r"(?:^|\s)TOTAL\s*[:\-]?\s*\$\s*([\d.,]{4,})", re.MULTILINE),
]
PALABRAS_NO_NOMBRE = ("FACTURA", "ELECTRONICA", "VENTA", "NIT", "FECHA", "TOTAL", "REGIMEN")


def _texto_util(t: str | None) -> bool:
    return bool(t) and sum(ch.isalnum() for ch in t) >= MIN_TEXTO_UTIL


def _con_pdfplumber(ruta: Path) -> tuple[str, list[list]]:
    import pdfplumber

    texto, tablas = [], []
    with pdfplumber.open(ruta) as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text(layout=True) or pagina.extract_text() or ""
            texto.append(t)
            for tabla in pagina.extract_tables() or []:
                tablas.extend(fila for fila in tabla if fila and any(fila))
    return "\n".join(texto), tablas


def _con_pypdf2(ruta: Path) -> str:
    from PyPDF2 import PdfReader

    r = PdfReader(str(ruta))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def _con_ocr(ruta: Path) -> str:
    """OCR de rescate para PDF escaneados. Lanza RuntimeError si falta Tesseract."""
    import pymupdf
    import pytesseract
    from PIL import Image

    trozos = []
    with pymupdf.open(ruta) as doc:
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            trozos.append(pytesseract.image_to_string(img, lang="spa+eng"))
    return "\n".join(trozos)


def extraer_texto(ruta: Path) -> tuple[str, list[list], str]:
    """Devuelve (texto, tablas, metodo). metodo dice qué intento funcionó."""
    tablas: list[list] = []
    try:
        texto, tablas = _con_pdfplumber(ruta)
        if _texto_util(texto):
            return texto, tablas, "pdfplumber"
    except Exception:
        pass
    try:
        texto = _con_pypdf2(ruta)
        if _texto_util(texto):
            return texto, tablas, "PyPDF2"
    except Exception:
        pass
    try:
        texto = _con_ocr(ruta)
        if _texto_util(texto):
            return texto, tablas, "OCR"
    except ImportError:
        return "", tablas, "SIN_LECTURA (instale pytesseract para el intento OCR)"
    except Exception as e:
        if "tesseract" in str(e).lower():
            return "", tablas, "SIN_LECTURA (instale Tesseract-OCR para leer PDF escaneados)"
    return "", tablas, "SIN_LECTURA"


def _buscar_paciente(texto: str) -> str | None:
    mayus = texto.upper()
    for rx in RE_PACIENTE:
        m = rx.search(mayus)
        if not m:
            continue
        nombre = " ".join(m.group(1).split())
        if len(nombre.split()) >= 2 and not any(p in nombre for p in PALABRAS_NO_NOMBRE):
            return nombre
    return None


def _buscar_total(texto: str) -> int | None:
    candidatos = [a_entero(m.group(1)) for rx in RE_TOTAL for m in rx.finditer(texto.upper())]
    candidatos = [c for c in candidatos if c]
    return max(candidatos) if candidatos else None  # el total es el mayor de los totales


RE_IMPORTE_EN_LINEA = re.compile(r"\d[\d.,]{2,}")


def _filas_del_texto(texto: str) -> list[list[str]]:
    """Las líneas del texto que parecen renglones de cobro, partidas en celdas.

    Muchas facturas electrónicas no dibujan la tabla: pdfplumber no encuentra
    nada con `extract_tables` y el detalle del servicio se perdía. Como el
    cotejo del cobro depende de ese renglón, se rescata del texto plano: cada
    línea con al menos un número largo se parte por espacios, igual que si
    fueran columnas.
    """
    filas = []
    for linea in texto.splitlines():
        limpia = " ".join(linea.split())
        if len(limpia) < 8 or not RE_IMPORTE_EN_LINEA.search(limpia):
            continue
        filas.append(limpia.split(" "))
    return filas


def extraer_datos_factura(ruta: Path | str) -> dict:
    """Datos de la factura para la redacción. Lo ilegible queda en None."""
    ruta = Path(ruta)
    texto, tablas, metodo = extraer_texto(ruta)
    servicios = [[str(c or "").strip() for c in fila] for fila in tablas[:200]]
    if texto:  # respaldo: el detalle también se busca en el texto plano
        servicios += _filas_del_texto(texto)[: max(0, 200 - len(servicios))]
    return dict(
        archivo=ruta.name,
        metodo=metodo,
        ok=bool(texto),
        paciente=_buscar_paciente(texto) if texto else None,
        total=_buscar_total(texto) if texto else None,
        servicios=servicios,
    )
