"""El valor aceptado no puede leerse como cero.

`completar_tramite_glosas_aceptadas` escribe el acta de las glosas que el
hospital aceptó. Su lector de pesos hacía `float(str(v).replace(",", ""))`:
solo quitaba comas, así que el formato colombiano lo destruía.

    "1.234.567"  →  ValueError  →  0     un millón se volvía cero
    "$114.900"   →  ValueError  →  0
    "50.000"     →  50                   dividido por mil
    "1.365,50"   →  1                    dividido por mil

Es peor que multiplicar por cien: un valor en cero pasa desapercibido en un
acta, y el hospital termina aceptando un monto que no declaró.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import completar_tramite_glosas_aceptadas as ctga  # noqa: E402


class TestValorAceptado:
    @pytest.mark.parametrize(
        "crudo,esperado",
        [
            ("1.234.567", 1234567),
            ("$114.900", 114900),
            ("50.000", 50000),
            ("2.500", 2500),
            ("1.365,50", 1365),
            ("1,234", 1234),
        ],
    )
    def test_lee_el_formato_colombiano(self, crudo, esperado):
        assert ctga.a_numero(crudo) == esperado

    def test_un_millon_no_puede_ser_cero(self):
        """El caso que más dolía: el valor desaparecía del acta."""
        assert ctga.a_numero("1.234.567") != 0
        assert ctga.a_numero("$114.900") != 0

    def test_no_divide_por_mil(self):
        assert ctga.a_numero("50.000") == 50000
        assert ctga.a_numero("50.000") != 50

    def test_acepta_numeros_ya_parseados(self):
        """openpyxl entrega celdas numéricas como int/float."""
        assert ctga.a_numero(114900) == 114900
        assert ctga.a_numero(114900.7) == 114900

    @pytest.mark.parametrize("basura", [None, "", "abc", "-"])
    def test_lo_ilegible_vale_cero(self, basura):
        assert ctga.a_numero(basura) == 0
