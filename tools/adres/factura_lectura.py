"""factura_lectura.py — Lectura de la Factura Electrónica DIAN (FEV XML).

La FEV de la DIAN viene en UBL 2.1 y en Colombia casi siempre como un
AttachedDocument que envuelve el Invoice **escapado** dentro de
`cbc:Description` (o en CDATA). En vez de pelear con el parseo XML estricto
(que falla por el anidamiento/escape), usamos un enfoque tolerante:

  1. Leer el archivo.
  2. Quitar marcadores CDATA y des-escapar entidades HTML una sola vez, de modo
     que el Invoice embebido (`&lt;cac:InvoiceLine&gt;...`) quede como tags
     reales en el texto.
  3. Extraer por regex cada bloque <InvoiceLine>...</InvoiceLine> y, dentro de
     cada uno, el código del prestador, la descripción, cantidad y valores.

Esto es robusto frente a namespaces (cac:/cbc: o sin prefijo) y al wrapping.

Sólo librería estándar (re, html).
"""

from __future__ import annotations

import html
import re
from pathlib import Path

# Bloque de una línea de factura (con o sin prefijo de namespace)
_RE_LINE = re.compile(
    r"<(?:\w+:)?InvoiceLine\b.*?</(?:\w+:)?InvoiceLine>", re.DOTALL | re.IGNORECASE
)

# Código del ítem: SellersItemIdentification (preferido) o StandardItemIdentification
_RE_COD_SELLER = re.compile(
    r"<(?:\w+:)?SellersItemIdentification\b.*?<(?:\w+:)?ID\b[^>]*>([^<]+)</(?:\w+:)?ID>",
    re.DOTALL | re.IGNORECASE,
)
_RE_COD_STD = re.compile(
    r"<(?:\w+:)?StandardItemIdentification\b.*?<(?:\w+:)?ID\b[^>]*>([^<]+)</(?:\w+:)?ID>",
    re.DOTALL | re.IGNORECASE,
)
_RE_DESC = re.compile(r"<(?:\w+:)?Description\b[^>]*>([^<]+)</(?:\w+:)?Description>", re.IGNORECASE)
_RE_QTY = re.compile(
    r"<(?:\w+:)?InvoicedQuantity\b[^>]*>([^<]+)</(?:\w+:)?InvoicedQuantity>", re.IGNORECASE
)
_RE_LINEAMT = re.compile(
    r"<(?:\w+:)?LineExtensionAmount\b[^>]*>([^<]+)</(?:\w+:)?LineExtensionAmount>", re.IGNORECASE
)
_RE_PRICEAMT = re.compile(
    r"<(?:\w+:)?PriceAmount\b[^>]*>([^<]+)</(?:\w+:)?PriceAmount>", re.IGNORECASE
)


def _texto_normalizado(ruta: Path) -> str:
    """Lee el archivo y des-escapa el Invoice embebido (CDATA o entidades)."""
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    # Quitar marcadores CDATA (dejando el contenido)
    contenido = contenido.replace("<![CDATA[", "").replace("]]>", "")
    # Si el Invoice viene escapado (&lt;...&gt;), des-escapar lo deja como tags.
    # Hacemos un solo unescape global: los tags ya reales no se ven afectados.
    if "&lt;" in contenido and "InvoiceLine" not in contenido.split("&lt;", 1)[0]:
        contenido = html.unescape(contenido)
    elif "InvoiceLine" not in contenido:
        # Por si está escapado sin el patrón anterior
        contenido = html.unescape(contenido)
    return contenido


def _primer(regexes, bloque: str) -> str:
    for rx in regexes:
        m = rx.search(bloque)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def cargar_factura_xml(ruta: Path) -> dict[str, dict]:
    """Devuelve {codigo_prestador: {descripcion, cantidad, vr_unitario, vr_total}}.

    Si un código se repite, conserva la última aparición.
    """
    texto = _texto_normalizado(ruta)
    if not texto:
        return {}

    items: dict[str, dict] = {}
    for bloque in _RE_LINE.findall(texto):
        cod = _primer([_RE_COD_SELLER, _RE_COD_STD], bloque)
        if not cod:
            continue
        items[cod.strip()] = {
            "descripcion": _primer([_RE_DESC], bloque),
            "cantidad": _primer([_RE_QTY], bloque),
            "vr_unitario": _primer([_RE_PRICEAMT], bloque),
            "vr_total": _primer([_RE_LINEAMT], bloque),
        }
    return items


def diagnostico(ruta: Path) -> dict:
    """Resumen para depurar por qué una factura no parsea (uso manual)."""
    try:
        crudo = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return {"error": str(e)}
    texto = _texto_normalizado(ruta)
    return {
        "archivo": ruta.name,
        "bytes": len(crudo),
        "tiene_AttachedDocument": "AttachedDocument" in crudo,
        "tiene_CDATA": "CDATA" in crudo,
        "tiene_Invoice_escapado": "&lt;" in crudo and "Invoice" in crudo,
        "InvoiceLine_en_crudo": crudo.count("InvoiceLine"),
        "InvoiceLine_tras_normalizar": texto.count("InvoiceLine"),
        "items_detectados": len(cargar_factura_xml(ruta)),
    }


def hallar_factura_xml(carpeta: Path) -> Path | None:
    """Encuentra el FEV XML en una carpeta de soportes (ignora FACOSTE)."""
    for p in sorted(carpeta.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".xml":
            continue
        nu = p.name.upper()
        if "FACOSTE" in nu:
            continue
        if "FACTURA" in nu or "FEV" in nu:
            return p
    return None


if __name__ == "__main__":
    # Uso: py factura_lectura.py <ruta_factura.xml>  → imprime diagnóstico
    import json
    import sys

    if len(sys.argv) < 2:
        sys.stderr.write("Uso: py factura_lectura.py <factura.xml>\n")
        sys.exit(1)
    d = diagnostico(Path(sys.argv[1]))
    print(json.dumps(d, ensure_ascii=False, indent=2))
    items = cargar_factura_xml(Path(sys.argv[1]))
    for i, (cod, v) in enumerate(list(items.items())[:5], 1):
        print(f"  ej[{i}] {cod}: {v}")
