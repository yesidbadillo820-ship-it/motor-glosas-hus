"""Tests de seguridad para `_safe_join` del endpoint /soportes-auto/upload-bulk.

Path traversal en este endpoint es crítico: un agente comprometido o
un usuario auditor malintencionado podría escribir archivos arbitrarios
en disco si la validación falla. Cubre los vectores conocidos.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routers.soportes import _safe_join


@pytest.fixture
def base(tmp_path: Path) -> Path:
    raiz = tmp_path / "soportes"
    raiz.mkdir()
    return raiz


class TestSafeJoinPermitidos:
    def test_path_simple(self, base: Path):
        r = _safe_join(base, "ABRIL 2026/foo.pdf")
        assert r is not None
        assert str(r).startswith(str(base.resolve()))

    def test_separadores_windows(self, base: Path):
        r = _safe_join(base, "ABRIL 2026\\1. DD FACTURACION\\ESCANEO\\FAMISANAR\\ENV-1\\FEV.pdf")
        assert r is not None

    def test_slashes_consecutivos(self, base: Path):
        r = _safe_join(base, "ABRIL 2026//foo.pdf")
        assert r is not None


class TestSafeJoinBloqueados:
    def test_path_traversal_simple(self, base: Path):
        assert _safe_join(base, "../etc/passwd") is None

    def test_path_traversal_profundo(self, base: Path):
        assert _safe_join(base, "ABRIL/../../etc/passwd") is None

    def test_path_traversal_windows(self, base: Path):
        assert _safe_join(base, "..\\..\\Windows\\System32\\config") is None

    def test_path_absoluto_posix(self, base: Path):
        # Absoluto Linux: lstrip lo convierte en relativo, pero el
        # resultado debe seguir bajo base. `/etc/passwd` → `etc/passwd`
        # que es válido bajo base. La validación absoluta real es la
        # de `..`. Test específico de drive letter:
        assert _safe_join(base, "C:/Windows") is None
        assert _safe_join(base, "C:\\Windows") is None

    def test_drive_letter_minuscula(self, base: Path):
        assert _safe_join(base, "y:/foo.pdf") is None

    def test_byte_nulo(self, base: Path):
        assert _safe_join(base, "foo\x00.pdf") is None

    def test_vacio(self, base: Path):
        assert _safe_join(base, "") is None

    def test_solo_punto(self, base: Path):
        assert _safe_join(base, ".") is None

    def test_solo_dospuntos(self, base: Path):
        assert _safe_join(base, "..") is None

    def test_path_largo(self, base: Path):
        assert _safe_join(base, "a/" * 300) is None  # >500 chars

    def test_segmento_punto_intermedio(self, base: Path):
        assert _safe_join(base, "ABRIL/./foo.pdf") is None
