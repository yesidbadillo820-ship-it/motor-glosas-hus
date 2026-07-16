"""
Pruebas de nucleo.pdf_tools (caja de herramientas PDF de la Suite Cartera HUS).

Se salta automáticamente si PyMuPDF (fitz) no está instalado, para no romper
entornos que no usan la Suite. En CI se instala vía requirements-dev.txt.
"""

import os
import sys

import pytest

SUITE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "tools", "suite_cartera_hus")
)
if SUITE not in sys.path:
    sys.path.insert(0, SUITE)

fitz = pytest.importorskip("fitz")

from nucleo import pdf_tools  # noqa: E402


def _silencio(_):
    pass


@pytest.fixture
def pdf5(tmp_path):
    """Un PDF de 5 páginas con un NIT reconocible en cada una."""
    ruta = str(tmp_path / "factura.pdf")
    doc = fitz.open()
    for i in range(5):
        doc.new_page().insert_text((72, 72), "Factura HUS pagina %d NIT 900226715" % (i + 1))
    doc.save(ruta)
    doc.close()
    return ruta


@pytest.fixture
def pdf3(tmp_path):
    ruta = str(tmp_path / "glosa.pdf")
    doc = fitz.open()
    for i in range(3):
        doc.new_page().insert_text((72, 72), "Glosa pagina %d" % (i + 1))
    doc.save(ruta)
    doc.close()
    return ruta


def _paginas(ruta):
    doc = fitz.open(ruta)
    n = doc.page_count
    doc.close()
    return n


# ------------------------------------------------------------- parse_paginas


def test_parse_paginas_rangos():
    assert pdf_tools.parse_paginas("1-3,5", 10) == [0, 1, 2, 4]


def test_parse_paginas_abierto_y_todas():
    assert pdf_tools.parse_paginas("8-", 10) == [7, 8, 9]
    assert pdf_tools.parse_paginas("todas", 3) == [0, 1, 2]


def test_parse_paginas_sin_duplicados_y_acotado():
    assert pdf_tools.parse_paginas("2,2,99", 3) == [1]


# ------------------------------------------------------------- operaciones


def test_unir(pdf5, pdf3, tmp_path):
    out = str(tmp_path / "u.pdf")
    pdf_tools.unir([pdf5, pdf3], out, log=_silencio)
    assert _paginas(out) == 8


def test_unir_exige_dos(pdf5, tmp_path):
    with pytest.raises(ValueError):
        pdf_tools.unir([pdf5], str(tmp_path / "x.pdf"), log=_silencio)


def test_extraer_paginas(pdf5, tmp_path):
    out = pdf_tools.extraer_paginas(pdf5, "1-2,4", str(tmp_path / "e.pdf"), log=_silencio)
    assert _paginas(out) == 3


def test_eliminar_paginas(pdf5, tmp_path):
    out = pdf_tools.eliminar_paginas(pdf5, "2,4", str(tmp_path / "el.pdf"), log=_silencio)
    assert _paginas(out) == 3


def test_eliminar_todas_falla(pdf5, tmp_path):
    with pytest.raises(ValueError):
        pdf_tools.eliminar_paginas(pdf5, "1-5", str(tmp_path / "z.pdf"), log=_silencio)


def test_reordenar(pdf5, tmp_path):
    out = pdf_tools.reordenar(pdf5, [5, 4, 3, 2, 1], str(tmp_path / "r.pdf"), log=_silencio)
    assert _paginas(out) == 5


def test_dividir(pdf5, tmp_path):
    partes = pdf_tools.dividir(pdf5, str(tmp_path / "div"), cada=2, log=_silencio)
    assert len(partes) == 3  # 2+2+1
    assert all(os.path.exists(p) for p in partes)


def test_rotar(pdf5, tmp_path):
    out = pdf_tools.rotar(pdf5, 90, None, str(tmp_path / "ro.pdf"), log=_silencio)
    doc = fitz.open(out)
    assert doc[0].rotation == 90
    doc.close()


def test_rotar_grados_invalidos(pdf5, tmp_path):
    with pytest.raises(ValueError):
        pdf_tools.rotar(pdf5, 45, None, str(tmp_path / "b.pdf"), log=_silencio)


def test_comprimir(pdf5, tmp_path):
    out = pdf_tools.comprimir(pdf5, str(tmp_path / "c.pdf"), log=_silencio)
    assert os.path.exists(out)


def test_proteger_y_desbloquear(pdf5, tmp_path):
    prot = pdf_tools.proteger(pdf5, "clave123", str(tmp_path / "p.pdf"), log=_silencio)
    doc = fitz.open(prot)
    assert doc.needs_pass
    doc.close()
    des = pdf_tools.desbloquear(prot, "clave123", str(tmp_path / "d.pdf"), log=_silencio)
    doc = fitz.open(des)
    assert not doc.needs_pass
    doc.close()


def test_desbloquear_clave_incorrecta(pdf5, tmp_path):
    prot = pdf_tools.proteger(pdf5, "buena", str(tmp_path / "p.pdf"), log=_silencio)
    with pytest.raises(ValueError):
        pdf_tools.desbloquear(prot, "mala", str(tmp_path / "d.pdf"), log=_silencio)


def test_censurar_borra_el_texto(pdf5, tmp_path):
    out = pdf_tools.censurar(pdf5, ["900226715"], str(tmp_path / "ce.pdf"), log=_silencio)
    doc = fitz.open(out)
    restantes = sum(len(p.search_for("900226715")) for p in doc)
    doc.close()
    assert restantes == 0


def test_marca_agua(pdf5, tmp_path):
    out = pdf_tools.marca_agua(pdf5, "COPIA HUS", str(tmp_path / "m.pdf"), log=_silencio)
    assert os.path.exists(out) and _paginas(out) == 5


def test_numerar(pdf5, tmp_path):
    out = pdf_tools.numerar(pdf5, str(tmp_path / "n.pdf"), log=_silencio)
    assert _paginas(out) == 5


def test_recortar(pdf5, tmp_path):
    out = pdf_tools.recortar(pdf5, 0.1, str(tmp_path / "rc.pdf"), log=_silencio)
    assert os.path.exists(out)


def test_imagenes_ida_y_vuelta(pdf5, tmp_path):
    imgs = pdf_tools.pdf_a_imagenes(pdf5, str(tmp_path / "img"), dpi=72, log=_silencio)
    assert len(imgs) == 5
    out = pdf_tools.imagenes_a_pdf(imgs, str(tmp_path / "vuelta.pdf"), log=_silencio)
    assert _paginas(out) == 5


def test_info(pdf5):
    d = pdf_tools.info(pdf5, log=_silencio)
    assert d["paginas"] == 5 and d["cifrado"] is False


def test_renombrar_extension(pdf5, tmp_path):
    out = pdf_tools.renombrar_extension(pdf5, ".cmd", str(tmp_path / "factura.cmd"), log=_silencio)
    assert out.endswith(".cmd") and os.path.exists(out)
    assert os.path.getsize(out) == os.path.getsize(pdf5)
