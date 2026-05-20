"""Regresión del bug de corrupción de valores monetarios en
recepcion_service._a_float (antes borraba '.'/','/'-' → ×100 sin signo)."""

import pytest

from app.services.recepcion_service import _a_float


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        # Formato colombiano: '.' miles, ',' decimal
        ("1.234.567,89", 1234567.89),
        ("1.234,50", 1234.50),
        ("0,99", 0.99),
        ("12.345", 12345.0),  # solo miles, sin decimales
        ("2.500", 2500.0),
        # Formato US: ',' miles, '.' decimal
        ("1,234,567.89", 1234567.89),
        ("1234.56", 1234.56),
        # Moneda / espacios / signo
        ("$ 1.234,50", 1234.50),
        ("  2.500  ", 2500.0),
        ("-500", -500.0),
        ("(1.234,50)", -1234.50),  # negativo contable entre paréntesis
        # Numéricos nativos y vacíos
        (1234, 1234.0),
        (1234.5, 1234.5),
        (None, 0.0),
        ("", 0.0),
        ("abc", 0.0),
        ("1234", 1234.0),
    ],
)
def test_a_float_preserva_decimales_y_signo(entrada, esperado):
    assert abs(_a_float(entrada) - esperado) < 0.001, (
        f"_a_float({entrada!r}) = {_a_float(entrada)} (esperado {esperado})"
    )


def test_a_float_no_infla_x100_el_bug_original():
    """El bug: '1.234.567,89' se volvía 123456789 (×100). Debe ser
    1234567.89, no un entero gigante."""
    r = _a_float("1.234.567,89")
    assert r == 1234567.89
    assert r != 123456789.0
