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


def test_tambien_cmd_crea_copia_identica(tmp_path):
    _hacer_pdf(tmp_path / "c" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "b.pdf", paginas=2)
    mod = _cargar_modulo()

    assert mod.main([str(tmp_path), "--tambien-cmd"]) == 0
    pdf = tmp_path / "c" / "_UNIDO_c.pdf"
    cmd = tmp_path / "c" / "_UNIDO_c.cmd"
    assert pdf.exists() and cmd.exists()
    # La copia .cmd es byte a byte el mismo PDF (solo cambia la extensión).
    assert cmd.read_bytes() == pdf.read_bytes()
    assert cmd.read_bytes().startswith(b"%PDF")

    # Re-corrida: la copia .cmd no se traga como entrada ni duplica páginas.
    assert mod.main([str(tmp_path), "--tambien-cmd"]) == 0
    assert _num_paginas(pdf) == 3
    assert cmd.read_bytes() == pdf.read_bytes()


def test_tambien_cmd_en_simulacro_no_escribe(tmp_path):
    _hacer_pdf(tmp_path / "c" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "b.pdf", paginas=1)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--tambien-cmd", "--simulacro"]) == 0
    assert not (tmp_path / "c" / "_UNIDO_c.pdf").exists()
    assert not (tmp_path / "c" / "_UNIDO_c.cmd").exists()


def test_sin_tambien_cmd_no_deja_copia(tmp_path):
    _hacer_pdf(tmp_path / "c" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "b.pdf", paginas=1)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert (tmp_path / "c" / "_UNIDO_c.pdf").exists()
    assert not (tmp_path / "c" / "_UNIDO_c.cmd").exists()


def test_cmd_existente_se_refresca_aunque_falte_la_bandera(tmp_path):
    """Si hay copia .cmd previa, re-correr SIN --tambien-cmd no la deja obsoleta."""
    _hacer_pdf(tmp_path / "c" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c" / "b.pdf", paginas=1)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--tambien-cmd"]) == 0
    pdf = tmp_path / "c" / "_UNIDO_c.pdf"
    cmd = tmp_path / "c" / "_UNIDO_c.cmd"
    assert cmd.read_bytes() == pdf.read_bytes()

    # Cambia el contenido de la carpeta y re-corre sin la bandera (flujo manual
    # del README): el .cmd debe refrescarse junto con el .pdf, no divergir.
    _hacer_pdf(tmp_path / "c" / "z_nuevo.pdf", paginas=5)
    assert mod.main([str(tmp_path)]) == 0
    assert _num_paginas(pdf) == 7
    assert cmd.read_bytes() == pdf.read_bytes()


def test_fallo_al_copiar_cmd_no_aborta_la_corrida(tmp_path):
    """Un obstáculo en el destino .cmd de una carpeta no debe tumbar el resto."""
    _hacer_pdf(tmp_path / "c1" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c1" / "b.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c2" / "a.pdf", paginas=1)
    _hacer_pdf(tmp_path / "c2" / "b.pdf", paginas=1)
    # Obstáculo: un DIRECTORIO ocupa el nombre del .cmd destino en c1.
    (tmp_path / "c1" / "_UNIDO_c1.cmd").mkdir()

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--tambien-cmd"]) == 0
    # c1: el PDF consolidado sí se generó aunque su copia .cmd falló.
    assert (tmp_path / "c1" / "_UNIDO_c1.pdf").exists()
    # c2 se procesó completo a pesar del fallo en c1.
    assert (tmp_path / "c2" / "_UNIDO_c2.pdf").exists()
    assert (tmp_path / "c2" / "_UNIDO_c2.cmd").exists()
    # No quedan .tmp huérfanos.
    assert not list(tmp_path.rglob("*.tmp"))


def test_comprimir_reduce_escaneos_color(tmp_path):
    """--comprimir baja el peso de escaneos color de alta resolución sin perder páginas."""
    fitz = pytest.importorskip("fitz")
    import os as _os

    # "Escaneo" a color ~300 dpi: JPEG ruidoso de alta calidad (pesado a propósito).
    w, h = 2400, 3400
    pix = fitz.Pixmap(fitz.csRGB, w, h, _os.urandom(w * h * 3), False)
    jpeg = pix.tobytes("jpeg", jpg_quality=95)
    origen = fitz.open()
    page = origen.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=jpeg)
    carpeta = tmp_path / "c"
    carpeta.mkdir()
    origen.save(str(carpeta / "a.pdf"))
    origen.save(str(carpeta / "b.pdf"))
    origen.close()
    peso_fuentes = sum(p.stat().st_size for p in carpeta.glob("*.pdf"))

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--tambien-cmd", "--comprimir"]) == 0
    pdf = carpeta / "_UNIDO_c.pdf"
    cmd = carpeta / "_UNIDO_c.cmd"
    assert _num_paginas(pdf) == 2
    # Reducción real (300→150 dpi baja 4x los píxeles): exigimos al menos 30%.
    assert pdf.stat().st_size < peso_fuentes * 0.7
    # La copia .cmd sale de la versión YA comprimida.
    assert cmd.read_bytes() == pdf.read_bytes()


def test_comprimir_nunca_infla_un_pdf_ya_optimo(tmp_path):
    """En PDFs sin nada que ganar, --comprimir no daña ni agranda el resultado."""
    pytest.importorskip("fitz")
    for sub in ("con", "sin"):
        _hacer_pdf(tmp_path / sub / "a.pdf", paginas=2)
        _hacer_pdf(tmp_path / sub / "b.pdf", paginas=1)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path / "con"), "--comprimir"]) == 0
    assert mod.main([str(tmp_path / "sin")]) == 0
    con = tmp_path / "con" / "_UNIDO_con.pdf"
    sin = tmp_path / "sin" / "_UNIDO_sin.pdf"
    assert _num_paginas(con) == 3 == _num_paginas(sin)
    # La red de seguridad garantiza que comprimir jamás agranda el archivo.
    assert con.stat().st_size <= sin.stat().st_size
    assert not list((tmp_path / "con").rglob("*.tmp"))


def test_motor_embebido_en_cmd_identico_al_py():
    """La copia embebida tras #PYSTART# en UNIR_PDFS.cmd debe ser el .py exacto.

    Es el código que ejecuta la mayoría de usuarios (copian SOLO el .cmd): si
    alguien edita el .py y olvida regenerar el .cmd, este test lo detecta.
    """
    cmd_path = _RAIZ / "tools" / "UNIR_PDFS.cmd"
    lineas = cmd_path.read_text(encoding="utf-8").splitlines()
    marcador = "#PY" + "START#"  # partido para no autodetectarse
    idx = next(i for i, ln in enumerate(lineas) if marcador in ln)
    embebido = "\n".join(lineas[idx + 1 :]).strip("\n")
    fuente = _MOTOR.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    assert embebido == fuente, (
        "La copia embebida en tools/UNIR_PDFS.cmd difiere de tools/unir_pdfs_carpetas.py. "
        "Regenera el .cmd (encabezado batch + contenido del .py en CRLF)."
    )
