"""Tests del reparador de XML de notas crédito para el portal de SAVIA
(tools/reparar_xml_nc_ascii.py): convierte los acentos a entidades numéricas
dejando el archivo 100% ASCII, verificando que los documentos embebidos
(CDATA con las firmas DIAN) queden canónicamente idénticos."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest  # noqa: F401

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import reparar_xml_nc_ascii as rep  # noqa: E402

_XML = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n'
    '<AttachedDocument xmlns:cbc="urn:x"><cbc:Nota atributo="Dirección">'
    "Factura Electrónica</cbc:Nota><cbc:Contenido><![CDATA["
    '<?xml version="1.0" encoding="utf-8"?><CreditNote xmlns:cbc="urn:x">'
    "<cbc:ID>332660</cbc:ID><cbc:Nota>SEGÚN ACTA — CONCILIACIÓN año</cbc:Nota>"
    "</CreditNote>]]></cbc:Contenido></AttachedDocument>"
)


def test_a_ascii_con_entidades():
    assert rep.a_ascii_con_entidades("ó") == "&#243;"
    assert rep.a_ascii_con_entidades("abc 123") == "abc 123"


def test_verificar_equivalencia_ok():
    arreglado = rep.a_ascii_con_entidades(_XML)
    assert all(ord(c) < 128 for c in arreglado)
    assert rep.verificar_equivalencia(_XML, arreglado) == []


def test_verificar_detecta_cambio_en_embebido():
    arreglado = rep.a_ascii_con_entidades(_XML).replace("332660", "999999")
    problemas = rep.verificar_equivalencia(_XML, arreglado)
    assert any("embebido" in p for p in problemas)


def test_reparar_archivo_end_to_end(tmp_path):
    origen = tmp_path / "NC332660.xml"
    origen.write_bytes(_XML.encode("utf-8"))
    destino = tmp_path / "ARREGLADOS" / "NC332660.xml"
    escrito, msg = rep.reparar_archivo(origen, destino)
    assert escrito, msg
    data = destino.read_bytes()
    assert all(b < 128 for b in data)  # 100% ASCII
    # El contenido parsea y resuelve a los MISMOS caracteres.
    raiz = ET.fromstring(data.decode("ascii"))
    assert raiz.find(".//{urn:x}Nota").text == "Factura Electrónica"
    # El embebido queda canónicamente idéntico.
    import re

    inner_fix = re.search(r"<!\[CDATA\[(.*?)\]\]>", data.decode("ascii"), re.S).group(1)
    inner_orig = re.search(r"<!\[CDATA\[(.*?)\]\]>", _XML, re.S).group(1)
    assert ET.canonicalize(inner_fix) == ET.canonicalize(inner_orig)


def test_reparar_archivo_ascii_no_se_toca(tmp_path):
    origen = tmp_path / "NC1.xml"
    origen.write_bytes(b'<?xml version="1.0"?><a>sin acentos</a>')
    escrito, msg = rep.reparar_archivo(origen, tmp_path / "out" / "NC1.xml")
    assert not escrito
    assert "ASCII" in msg


def test_rescata_archivo_ya_danado_latin1(tmp_path):
    # Un XML que YA venía con bytes latin-1 sueltos (inválido como UTF-8).
    origen = tmp_path / "NC2.xml"
    origen.write_bytes('<?xml version="1.0"?><a>Facturaci\xf3n</a>'.encode("latin-1"))
    destino = tmp_path / "out" / "NC2.xml"
    escrito, msg = rep.reparar_archivo(origen, destino)
    assert escrito
    assert "rescató" in msg
    raiz = ET.fromstring(destino.read_bytes().decode("ascii"))
    assert raiz.text == "Facturación"


def test_cli_carpeta(tmp_path):
    (tmp_path / "NC_A.xml").write_bytes(_XML.encode("utf-8"))
    (tmp_path / "NC_B.xml").write_bytes(b'<?xml version="1.0"?><a>plano</a>')
    rc = rep.main(["--entrada", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "ARREGLADOS" / "NC_A.xml").is_file()
    assert not (tmp_path / "ARREGLADOS" / "NC_B.xml").exists()  # no lo necesitaba
