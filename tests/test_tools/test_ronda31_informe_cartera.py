"""Ronda 31: saneo de celdas Excel / párrafos Word en el informe de baja
de cartera (tools/generar_informe_baja_cartera.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parents[2] / "tools" / "generar_informe_baja_cartera.py"

pytest.importorskip("docx")  # el tool importa python-docx a nivel módulo


def _cargar():
    spec = importlib.util.spec_from_file_location("_gibc_test", _RUTA)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_gibc_test"] = m  # dataclasses necesitan el módulo registrado
    spec.loader.exec_module(m)
    return m


gibc = _cargar()


class TestCeldaSegura:
    def test_neutraliza_formula(self):
        for pref in ("=", "+", "-", "@"):
            assert gibc._celda_segura(pref + "HYPERLINK(1)").startswith("'" + pref)

    def test_numeros_intactos(self):
        assert gibc._celda_segura(1_500_000) == 1_500_000
        assert gibc._celda_segura(1500.5) == 1500.5

    def test_quita_control_chars(self):
        assert "\x00" not in gibc._celda_segura("obs\x00erv\x07ación")
        assert "ación" in gibc._celda_segura("obs\x00erv\x07ación")

    def test_texto_normal_intacto(self):
        assert gibc._celda_segura("FACTURA 900123") == "FACTURA 900123"


class TestLimpiarParrafo:
    def test_quita_control_chars(self):
        assert gibc.limpiar_parrafo("a\x00b\x07c") == "abc"

    def test_colapsa_espacios(self):
        assert gibc.limpiar_parrafo("hola   \n  mundo") == "hola mundo"
