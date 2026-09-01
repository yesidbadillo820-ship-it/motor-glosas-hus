"""El acta de conciliación y la hoja maestra no pueden dividir por mil.

Los dos traían su propia copia del lector de pesos, con la misma condición
incompleta: `s.count(".") > 1`. Así, `"3.211.891"` (dos puntos) salía bien,
pero `"$ 950.000"` (un punto) se leía como **950,00** y `"2.500"` como
**2,50**.

Es exactamente el `950.000 → 950` que el auditor ya había visto en un informe
de cartera. Aparecía en tres sitios distintos por la misma causa: cada
herramienta escribió su propio lector.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import generar_acta_conciliacion_dispensario as acta  # noqa: E402
import hoja_maestra_conciliacion as hoja  # noqa: E402

CASOS = [
    ("3.211.891", 3211891.0),
    ("$ 950.000", 950000.0),
    ("50.000", 50000.0),
    ("2.500", 2500.0),
    ("114.900", 114900.0),
    ("1.365,50", 1365.50),
    ("1.234.567,89", 1234567.89),
]


@pytest.mark.parametrize("crudo,esperado", CASOS)
def test_el_acta_lee_bien(crudo, esperado):
    assert acta.num(crudo) == pytest.approx(esperado)


@pytest.mark.parametrize("crudo,esperado", CASOS)
def test_la_hoja_maestra_lee_bien(crudo, esperado):
    assert hoja._num(crudo) == pytest.approx(esperado)


def test_el_caso_del_informe_de_cartera():
    """`950.000` es novecientos cincuenta mil, no novecientos cincuenta."""
    assert acta.num("$ 950.000") == 950000.0
    assert hoja._num("$ 950.000") == 950000.0
    assert acta.num("$ 950.000") != 950.0


@pytest.mark.parametrize("basura", [None, "", "-", "None", "abc"])
def test_lo_ilegible_vale_cero(basura):
    assert acta.num(basura) == 0.0
    assert hoja._num(basura) == 0.0
