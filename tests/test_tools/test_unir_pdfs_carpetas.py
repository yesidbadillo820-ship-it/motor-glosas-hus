"""Pruebas del motor tools/unir_pdfs_carpetas.py (usado por UNIR_PDFS.cmd).

Genera PDF de prueba con reportlab (igual que test_pdf_service.py). Si no está
instalado, se skipean. Verifican: unión correcta con orden natural, omisión de
carpetas con menos del mínimo, tolerancia a PDF dañados e idempotencia.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_MOTOR = _RAIZ / "tools" / "unir_pdfs_carpetas.py"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("unir_pdfs_carpetas", _MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hacer_pdf(ruta: Path, paginas: int = 1) -> None:
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        pytest.skip("reportlab no instalado — no se puede generar PDF de prueba")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(ruta))
    for i in range(paginas):
        c.drawString(72, 720, f"{ruta.stem} pagina {i + 1}")
        c.showPage()
    c.save()


def _num_paginas(ruta: Path) -> int:
    mod = _cargar_modulo()
    PdfReader, _ = mod._cargar_lector_escritor()
    return len(PdfReader(str(ruta)).pages)


def test_une_por_carpeta_con_orden_natural(tmp_path):
    _hacer_pdf(tmp_path / "311131" / "01_factura.pdf", paginas=1)
    _hacer_pdf(tmp_path / "311131" / "02_epicrisis.pdf", paginas=2)
    _hacer_pdf(tmp_path / "311131" / "10_autorizacion.pdf", paginas=1)

    mod = _cargar_modulo()
    rc = mod.main([str(tmp_path)])
    assert rc == 0

    salida = tmp_path / "311131" / "_UNIDO_311131.pdf"
    assert salida.exists()
    # 1 + 2 + 1 = 4 páginas, en orden natural (2 antes que 10).
    assert _num_paginas(salida) == 4


def test_omite_carpeta_con_un_solo_pdf(tmp_path):
    _hacer_pdf(tmp_path / "solo" / "unico.pdf", paginas=1)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert not (tmp_path / "solo" / "_UNIDO_solo.pdf").exists()
    # Con --minimo 1 sí debe generarlo.
    assert mod.main([str(tmp_path), "--minimo", "1"]) == 0
    assert (tmp_path / "solo" / "_UNIDO_solo.pdf").exists()


def test_tolera_pdf_danado(tmp_path):
    _hacer_pdf(tmp_path / "c" / "bueno1.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "bueno2.pdf", paginas=1)
    (tmp_path / "c" / "roto.pdf").write_bytes(b"%PDF-1.4 no es un pdf real")

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    salida = tmp_path / "c" / "_UNIDO_c.pdf"
    assert salida.exists()
    # Solo las 2 páginas legibles; el dañado se omite sin abortar.
    assert _num_paginas(salida) == 2


def test_idempotente_no_reune_el_unido(tmp_path):
    _hacer_pdf(tmp_path / "c" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "b.pdf", paginas=1)
    mod = _cargar_modulo()

    assert mod.main([str(tmp_path)]) == 0
    salida = tmp_path / "c" / "_UNIDO_c.pdf"
    primera = _num_paginas(salida)
    # Segunda corrida: no debe tragarse el _UNIDO_ previo ni duplicar páginas.
    assert mod.main([str(tmp_path)]) == 0
    assert _num_paginas(salida) == primera == 2
    # Solo debe existir un _UNIDO_ en la carpeta.
    assert len(list((tmp_path / "c").glob("_UNIDO_*.pdf"))) == 1


def test_simulacro_no_escribe(tmp_path):
    _hacer_pdf(tmp_path / "c" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "b.pdf", paginas=1)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--simulacro"]) == 0
    assert not (tmp_path / "c" / "_UNIDO_c.pdf").exists()
