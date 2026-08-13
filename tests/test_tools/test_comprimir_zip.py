"""Pruebas del motor tools/comprimir_zip.py (usado por COMPRIMIR_ZIP.cmd)."""

from __future__ import annotations

import hashlib
import importlib.util
import zipfile
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_MOTOR = _RAIZ / "tools" / "comprimir_zip.py"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("comprimir_zip", _MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pdf_pesado(nbytes_seed: int = 0) -> bytes:
    fitz = pytest.importorskip("fitz")
    import os as _os

    w, h = 2200, 3000
    pix = fitz.Pixmap(fitz.csRGB, w, h, _os.urandom(w * h * 3), False)
    doc = fitz.open()
    doc.new_page(width=595, height=842).insert_image(
        fitz.Rect(0, 0, 595, 842), stream=pix.tobytes("jpeg", jpg_quality=95)
    )
    import io

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _jpg_grande() -> bytes:
    Image = pytest.importorskip("PIL.Image")
    import io
    import os as _os

    im = Image.frombytes("RGB", (2600, 1800), _os.urandom(2600 * 1800 * 3))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _crear_zip(ruta: Path, entradas: dict[str, bytes], nivel: int = 1) -> None:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED, compresslevel=nivel) as z:
        for nombre, datos in entradas.items():
            z.writestr(nombre, datos)


def test_comprime_pdf_e_imagen_y_respeta_lo_demas(tmp_path):
    pytest.importorskip("fitz")
    pytest.importorskip("PIL.Image")
    excel = b"PK\x03\x04" + b"hoja de calculo " * 400
    _crear_zip(
        tmp_path / "ENVIO.zip",
        {"soporte.pdf": _pdf_pesado(), "foto.jpg": _jpg_grande(), "informe.xlsx": excel},
    )
    antes = (tmp_path / "ENVIO.zip").stat().st_size

    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    lig = tmp_path / "ENVIO_LIGERO.zip"
    assert lig.exists()
    assert (tmp_path / "ENVIO.zip").exists()  # original intacto
    assert lig.stat().st_size < antes

    with zipfile.ZipFile(lig) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {"soporte.pdf", "foto.jpg", "informe.xlsx"}
        # el Excel NO cambió
        assert hashlib.md5(z.read("informe.xlsx")).hexdigest() == hashlib.md5(excel).hexdigest()
        # el PDF sigue siendo válido
        import fitz

        d = fitz.open(stream=z.read("soporte.pdf"), filetype="pdf")
        assert d.page_count == 1
        d.close()


def test_ignora_los_ligero(tmp_path):
    pytest.importorskip("fitz")
    _crear_zip(tmp_path / "cosa_LIGERO.zip", {"a.pdf": _pdf_pesado()})
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    # no debe generar cosa_LIGERO_LIGERO.zip
    assert not (tmp_path / "cosa_LIGERO_LIGERO.zip").exists()


def test_sin_margen_no_crea_ligero(tmp_path):
    _crear_zip(tmp_path / "chico.zip", {"a.xlsx": b"PK\x03\x04" + b"x" * 500}, nivel=9)
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert not (tmp_path / "chico_LIGERO.zip").exists()


def test_zip_corrupto_se_omite(tmp_path):
    (tmp_path / "roto.zip").write_bytes(b"PK\x03\x04 no es un zip")
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0  # no revienta
    assert not (tmp_path / "roto_LIGERO.zip").exists()


def test_simulacro_no_escribe(tmp_path):
    pytest.importorskip("fitz")
    _crear_zip(tmp_path / "ENVIO.zip", {"a.pdf": _pdf_pesado()})
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--simulacro"]) == 0
    assert not (tmp_path / "ENVIO_LIGERO.zip").exists()


def test_reemplazar_sobrescribe_el_original(tmp_path):
    pytest.importorskip("fitz")
    pytest.importorskip("PIL.Image")
    z = tmp_path / "ENVIO.zip"
    _crear_zip(z, {"soporte.pdf": _pdf_pesado(), "foto.jpg": _jpg_grande()})
    antes = z.stat().st_size
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--reemplazar"]) == 0
    assert not (tmp_path / "ENVIO_LIGERO.zip").exists()
    assert z.stat().st_size < antes  # el original quedó más liviano
    with zipfile.ZipFile(z) as zz:
        assert zz.testzip() is None


def test_motor_embebido_en_cmd_identico_al_py():
    cmd_path = _RAIZ / "tools" / "COMPRIMIR_ZIP.cmd"
    lineas = cmd_path.read_text(encoding="utf-8").splitlines()
    marcador = "#PY" + "START#"
    idx = next(i for i, ln in enumerate(lineas) if marcador in ln)
    embebido = "\n".join(lineas[idx + 1 :]).strip("\n")
    fuente = _MOTOR.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    assert embebido == fuente, (
        "La copia embebida en tools/COMPRIMIR_ZIP.cmd difiere de tools/comprimir_zip.py."
    )
