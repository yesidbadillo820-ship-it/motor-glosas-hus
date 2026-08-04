"""Ronda 31: condición C_RGO del validador FURIPS (tools/adres/validar_furips.py).

El campo 2 (RGO) admite {"0","1","6"}. "0" = NO es respuesta a glosa, así que
el radicado anterior (campo 1) NO es obligatorio. Antes `bool(c.get(2))` daba
True para "0" → falso positivo "campo obligatorio sin diligenciar".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parents[2] / "tools" / "adres" / "validar_furips.py"

pytest.importorskip("openpyxl")


def _cargar():
    spec = importlib.util.spec_from_file_location("_furips_test", _RUTA)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_furips_test"] = m
    spec.loader.exec_module(m)
    return m


furips = _cargar()


class TestCondicionCRGO:
    def test_rgo_cero_no_exige_radicado_anterior(self):
        obligatorio, _ = furips._evaluar_condicion("C_RGO", {2: "0"}, {})
        assert obligatorio is False

    def test_rgo_vacio_no_exige(self):
        obligatorio, _ = furips._evaluar_condicion("C_RGO", {2: ""}, {})
        assert obligatorio is False

    @pytest.mark.parametrize("rgo", ["1", "6"])
    def test_rgo_respuesta_a_glosa_si_exige(self, rgo):
        obligatorio, _ = furips._evaluar_condicion("C_RGO", {2: rgo}, {})
        assert obligatorio is True
