"""Pruebas del motor tools/pdf_a_cmd.py (usado por PDF_A_CMD.cmd).

Los "PDF" de prueba son archivos con la firma real %PDF-, que es lo único
que el motor inspecciona (no interpreta el contenido).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[2]
_MOTOR = _RAIZ / "tools" / "pdf_a_cmd.py"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("pdf_a_cmd", _MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hacer_pdf(ruta: Path, relleno: bytes = b"contenido") -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"%PDF-1.4\n" + relleno + b"\n%%EOF")


def test_convierte_cada_pdf_individual(tmp_path):
    # Carpeta con un SOLO PDF (el caso pedido) y otra con varios.
    _hacer_pdf(tmp_path / "HUS526504" / "FACTURA.pdf")
    _hacer_pdf(tmp_path / "HUS527934" / "a.pdf")
    _hacer_pdf(tmp_path / "HUS527934" / "b.pdf")

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0

    for origen in ("HUS526504/FACTURA.pdf", "HUS527934/a.pdf", "HUS527934/b.pdf"):
        o = tmp_path / origen
        copia = o.with_suffix(".cmd")
        assert copia.exists(), f"falta {copia}"
        assert copia.read_bytes() == o.read_bytes()
        assert o.exists()  # el original queda intacto


def test_idempotente_y_refresca_la_copia(tmp_path):
    pdf = tmp_path / "c" / "FACTURA.pdf"
    _hacer_pdf(pdf, b"version1")
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    copia = pdf.with_suffix(".cmd")
    assert b"version1" in copia.read_bytes()

    _hacer_pdf(pdf, b"version2")
    assert mod.main([str(tmp_path)]) == 0
    assert b"version2" in copia.read_bytes()
    assert not list(tmp_path.rglob("*.tmp"))


def test_jamas_pisa_un_cmd_que_no_es_pdf(tmp_path):
    _hacer_pdf(tmp_path / "c" / "UNIR_PDFS.pdf")
    bot = tmp_path / "c" / "UNIR_PDFS.cmd"
    bot.write_bytes(b"@echo off\r\nrem soy un script real\r\n")

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert bot.read_bytes().startswith(b"@echo off")


def test_refresca_la_copia_cmd_de_un_unido(tmp_path):
    """Sobre una carpeta ya procesada por UNIR_PDFS, refresca el _UNIDO_*.cmd
    (es contenido PDF) sin duplicar nada."""
    unido = tmp_path / "c" / "_UNIDO_c.pdf"
    _hacer_pdf(unido, b"consolidado")
    (tmp_path / "c" / "_UNIDO_c.cmd").write_bytes(unido.read_bytes())

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert (tmp_path / "c" / "_UNIDO_c.cmd").read_bytes() == unido.read_bytes()
    assert len(list((tmp_path / "c").glob("*.cmd"))) == 1


def test_simulacro_no_escribe(tmp_path):
    _hacer_pdf(tmp_path / "c" / "FACTURA.pdf")
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--simulacro"]) == 0
    assert not (tmp_path / "c" / "FACTURA.cmd").exists()


def test_motor_embebido_en_cmd_identico_al_py():
    """La copia embebida tras #PYSTART# en PDF_A_CMD.cmd debe ser el .py exacto."""
    cmd_path = _RAIZ / "tools" / "PDF_A_CMD.cmd"
    lineas = cmd_path.read_text(encoding="utf-8").splitlines()
    marcador = "#PY" + "START#"  # partido para no autodetectarse
    idx = next(i for i, ln in enumerate(lineas) if marcador in ln)
    embebido = "\n".join(lineas[idx + 1 :]).strip("\n")
    fuente = _MOTOR.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    assert embebido == fuente, (
        "La copia embebida en tools/PDF_A_CMD.cmd difiere de tools/pdf_a_cmd.py. "
        "Regenera el .cmd (encabezado batch + contenido del .py en CRLF)."
    )
