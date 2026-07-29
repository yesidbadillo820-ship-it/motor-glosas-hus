"""El lector de pesos de los bots debe coincidir con el del núcleo.

La prueba que importa es la última: el respaldo local —el que se usa cuando el
bot corre en el PC del hospital sin el paquete `app/`— tiene que dar lo mismo
que el núcleo. Si alguien toca uno de los dos y se separan, esta prueba lo
caza antes de que un Excel salga con los valores inflados.
"""

from __future__ import annotations

import pytest

from app.utils.moneda import parse_valor_cop
from tools._dinero import _respaldo, a_entero, a_numero

# (entrada, pesos esperados) — formatos que llegan de verdad en los archivos
# de los pagadores.
CASOS: list[tuple[str, float]] = [
    ("1.365,50", 1365.50),  # el que rompía SAVIA: daba 136.550
    ("$ 1.234,56", 1234.56),
    ("0,99", 0.99),
    ("20000.50", 20000.50),
    ("$114.900", 114900.0),
    ("2.177.341", 2177341.0),
    ("1.365", 1365.0),
    ("1365", 1365.0),
    ("2,177,341", 2177341.0),
    ("-1.500", -1500.0),
]


@pytest.mark.parametrize("crudo,esperado", CASOS)
def test_lee_los_formatos_reales(crudo, esperado):
    assert a_numero(crudo) == pytest.approx(esperado)


@pytest.mark.parametrize("crudo,esperado", CASOS)
def test_el_respaldo_coincide_con_el_nucleo(crudo, esperado):
    """Sin `app/` disponible el bot debe leer exactamente igual."""
    assert _respaldo(crudo) == pytest.approx(esperado)
    assert _respaldo(crudo) == pytest.approx(float(parse_valor_cop(crudo)))


def test_el_caso_que_inflaba_x100():
    """Un valor con centavos no puede multiplicarse por cien.

    `1.365,50` es mil trescientos sesenta y cinco pesos con cincuenta
    centavos, no ciento treinta y seis mil quinientos cincuenta.
    """
    assert a_entero("1.365,50") == 1365
    assert a_entero("1.365,50") != 136550


def test_entero_trunca_no_redondea():
    """El ERP nunca recibió centavos; redondear cambiaría el total del lote."""
    assert a_entero("1.365,90") == 1365
    assert a_entero("1.365,10") == 1365


@pytest.mark.parametrize("basura", [None, "", "   ", "abc", "-", ".", ",", True, False])
def test_lo_ilegible_vale_cero_y_no_revienta(basura):
    assert a_numero(basura) == 0.0
    assert a_entero(basura) == 0


def test_acepta_numeros_ya_parseados():
    """openpyxl entrega celdas numéricas como int/float, no como texto."""
    assert a_numero(1365) == 1365.0
    assert a_numero(1365.5) == 1365.5
    assert a_entero(1365.9) == 1365
