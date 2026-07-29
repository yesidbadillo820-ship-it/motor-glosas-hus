"""Pruebas del motor tools/partir_zip.py (usado por PARTIR_ZIP_30MB.cmd)."""

from __future__ import annotations

import glob
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]
_MOTOR = _RAIZ / "tools" / "partir_zip.py"


def _cargar_modulo():
    spec = importlib.util.spec_from_file_location("partir_zip", _MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pdf(paginas: int) -> bytes:
    """PDF con páginas de texto: comprimibles y livianas (~como un escaneo real,
    que a 150 dpi pesa mucho menos que el tope de una parte)."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for p in range(paginas):
        page = doc.new_page(width=595, height=842)
        for ln in range(40):
            page.insert_text(
                (50, 60 + ln * 18), f"Pagina {p + 1} linea {ln} soporte HUS", fontsize=11
            )
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _crear_zip(ruta: Path, entradas: dict[str, bytes]) -> None:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for nombre, datos in entradas.items():
            z.writestr(nombre, datos)


def _todas_las_partes(base: Path, stem: str) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(base / f"{stem}_parte*_de*.zip")))


def test_parte_muchos_archivos_sin_perder_nada(tmp_path):
    pytest.importorskip("fitz")
    entradas = {f"NE{i}/_UNIDO_NE{i}.pdf": _pdf(2) for i in range(6)}
    entradas["informe.xlsx"] = b"PK\x03\x04" + b"x" * 2000
    _crear_zip(tmp_path / "JULIO.zip", entradas)

    mod = _cargar_modulo()
    limite = 40_000
    assert mod.main([str(tmp_path), "--max-mb", "0.04", "--sin-comprimir"]) == 0

    partes = _todas_las_partes(tmp_path, "JULIO")
    assert len(partes) >= 2
    recuperados: set[str] = set()
    for p in partes:
        assert p.stat().st_size < limite  # cada parte bajo el tope
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            recuperados |= set(z.namelist())
    assert recuperados == set(entradas)  # ningún archivo perdido
    assert (tmp_path / "JULIO.zip").exists()  # original intacto


def test_parte_pdf_gigante_por_paginas(tmp_path):
    fitz = pytest.importorskip("fitz")
    _crear_zip(tmp_path / "GRANDE.zip", {"soporte.pdf": _pdf(20)})

    mod = _cargar_modulo()
    limite = 60_000
    assert mod.main([str(tmp_path), "--max-mb", "0.06", "--sin-comprimir"]) == 0

    partes = _todas_las_partes(tmp_path, "GRANDE")
    assert len(partes) >= 2
    total_pag = 0
    for p in partes:
        assert p.stat().st_size < limite
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            for n in z.namelist():
                d = fitz.open(stream=z.read(n), filetype="pdf")
                total_pag += d.page_count
                d.close()
    assert total_pag == 20  # las 20 páginas se conservan repartidas


def test_ignora_los_parte(tmp_path):
    pytest.importorskip("fitz")
    _crear_zip(tmp_path / "cosa_parte1_de3.zip", {"a.pdf": _pdf(3)})
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--max-mb", "0.3", "--sin-comprimir"]) == 0
    # no debe re-partir un *_parte*_de*.zip
    assert not glob.glob(str(tmp_path / "cosa_parte1_de3_parte*"))


def test_simulacro_no_escribe(tmp_path):
    pytest.importorskip("fitz")
    _crear_zip(tmp_path / "JULIO.zip", {"a.pdf": _pdf(6)})
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path), "--max-mb", "0.3", "--simulacro"]) == 0
    assert not _todas_las_partes(tmp_path, "JULIO")


def test_zip_corrupto_se_omite(tmp_path):
    (tmp_path / "roto.zip").write_bytes(b"PK\x03\x04 no es zip")
    mod = _cargar_modulo()
    assert mod.main([str(tmp_path)]) == 0
    assert not _todas_las_partes(tmp_path, "roto")


def test_motor_embebido_en_cmd_identico_al_py():
    cmd_path = _RAIZ / "tools" / "PARTIR_ZIP_30MB.cmd"
    lineas = cmd_path.read_text(encoding="utf-8").splitlines()
    marcador = "#PY" + "START#"
    idx = next(i for i, ln in enumerate(lineas) if marcador in ln)
    embebido = "\n".join(lineas[idx + 1 :]).strip("\n")
    fuente = _MOTOR.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    assert embebido == fuente, (
        "La copia embebida en tools/PARTIR_ZIP_30MB.cmd difiere de tools/partir_zip.py."
    )
