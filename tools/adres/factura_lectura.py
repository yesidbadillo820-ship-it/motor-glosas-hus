"""factura_lectura.py — Lectura de la Factura Electrónica DIAN (FEV XML).

La FEV de la DIAN viene en formato UBL 2.1, y en Colombia normalmente como
un AttachedDocument que envuelve el Invoice **escapado** dentro de
`cbc:Description` (o en CDATA). Este módulo maneja ambos casos.

Extrae, por cada InvoiceLine, el código del prestador (SellersItemIdentification),
la descripción, la cantidad y los valores. Es el complemento natural del RIPS
para llenar la descripción y el código SOAT que el RIPS no trae.

Sólo librería estándar (re, xml.etree.ElementTree, html).
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# Namespaces UBL 2.1
NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def _extraer_invoice_xml(contenido: str) -> str:
    """Si es un AttachedDocument con el Invoice escapado/CDATA adentro, lo
    extrae. Si ya es un Invoice plano, devuelve el contenido tal cual.
    """
    # Caso 1: ya es un Invoice / NoteCredit directo
    if re.search(r"<(?:[a-zA-Z]+:)?Invoice[\s>]", contenido):
        return contenido

    # Caso 2: AttachedDocument con CDATA explícito
    m = re.search(
        r"<!\[CDATA\[(.*?(?:<\?xml.*?\?>)?.*?<(?:[a-zA-Z]+:)?Invoice.*?</(?:[a-zA-Z]+:)?Invoice>.*?)\]\]>",
        contenido,
        re.DOTALL,
    )
    if m:
        return m.group(1)

    # Caso 3: AttachedDocument con el Invoice escapado dentro de cbc:Description
    m = re.search(
        r"<cbc:Description[^>]*>([^<]*?&lt;(?:[a-zA-Z]+:)?Invoice.*?&lt;/(?:[a-zA-Z]+:)?Invoice&gt;[^<]*?)</cbc:Description>",
        contenido,
        re.DOTALL,
    )
    if m:
        return html.unescape(m.group(1))

    # Caso 4: AttachedDocument que tiene el Invoice como cbc:Description sin namespace
    m = re.search(
        r"<Description[^>]*>([^<]*?&lt;(?:[a-zA-Z]+:)?Invoice.*?&lt;/(?:[a-zA-Z]+:)?Invoice&gt;[^<]*?)</Description>",
        contenido,
        re.DOTALL,
    )
    if m:
        return html.unescape(m.group(1))

    return contenido  # último recurso: devolvemos el contenido crudo


def _texto(elem, *xpaths) -> str:
    """Devuelve el primer texto encontrado para alguno de los xpaths."""
    for xp in xpaths:
        n = elem.find(xp, NS)
        if n is not None and n.text:
            return n.text.strip()
    return ""


def cargar_factura_xml(ruta: Path) -> dict[str, dict]:
    """Lee la FEV XML y devuelve {codigo_vendedor: {desc, cantidad, vr_unit, vr_total}}.

    Si un código del vendedor se repite en varias líneas (ej. el mismo insumo
    facturado en 2 líneas), conserva la última (idempotente para uso normal).
    """
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    xml_invoice = _extraer_invoice_xml(contenido)
    try:
        root = ET.fromstring(xml_invoice)
    except ET.ParseError:
        return {}

    items: dict[str, dict] = {}
    # Iteramos sobre InvoiceLine (con o sin namespace)
    for line in root.iter():
        tag = line.tag.split("}")[-1]
        if tag != "InvoiceLine":
            continue
        cod = _texto(
            line,
            "cac:Item/cac:SellersItemIdentification/cbc:ID",
            "cac:Item/cac:StandardItemIdentification/cbc:ID",
        )
        if not cod:
            continue
        desc = _texto(line, "cac:Item/cbc:Description")
        cantidad = _texto(line, "cbc:InvoicedQuantity")
        vr_total = _texto(line, "cbc:LineExtensionAmount")
        vr_unit = _texto(line, "cac:Price/cbc:PriceAmount")
        items[cod.strip()] = {
            "descripcion": desc,
            "cantidad": cantidad,
            "vr_unitario": vr_unit,
            "vr_total": vr_total,
        }
    return items


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
