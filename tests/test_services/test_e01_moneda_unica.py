"""Épica E01 — Un solo parser de moneda (Principio N.º 1: SINAC CORE primero).

El sistema tenía cuatro implementaciones del mismo parser de pesos, cada una
con sus propios puntos ciegos. Dos de ellas se equivocaban en plata:

  · `tools/tablero_cartera._parse_valor` solo quitaba los puntos de miles
    cuando había MÁS DE UNO, así que `950.000` se leía como **950 pesos** —
    y ese número viajaba al informe de cartera de gerencia.
  · `tarifas_excel_parser` y `tarifas_contratadas` leían como CERO el
    separador de miles con apóstrofo (`1'500.000`) y las cifras en palabras
    (`850 millones`). Una tarifa en cero se propaga a todo el dictamen.

Ahora los tres delegan en `app.utils.moneda.parse_valor_cop`. El tablero, que
también corre suelto en el PC del hospital, conserva un respaldo local que
DEBE dar el mismo número que el núcleo.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.api.routers.tarifas_contratadas import _normalizar_valor as valor_contratadas
from app.services.tarifas_excel_parser import _normalizar_valor as valor_excel
from app.utils.moneda import parse_valor_cop

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tablero():
    spec = importlib.util.spec_from_file_location("_tc", RAIZ / "tools" / "tablero_cartera.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["_tc"] = m
    spec.loader.exec_module(m)
    return m


# Formatos que el auditor teclea o que exportan los portales.
CASOS = [
    "950.000",
    "1.500",
    "1.234.567",
    "1.500,00",
    "1.365,50",
    "$ 2.000",
    "2.500.000,00",
    "1,234,567.89",
    "-1.500",
    "1234567",
    "20000.50",
    "0.99",
    "7.70",
    "12.345",
    "",
    "N/A",
]


class TestUnSoloParser:
    @pytest.mark.parametrize("entrada", CASOS)
    def test_tarifas_excel_coincide_con_el_nucleo(self, entrada):
        assert valor_excel(entrada) == parse_valor_cop(entrada)

    @pytest.mark.parametrize("entrada", CASOS)
    def test_tarifas_contratadas_coincide_con_el_nucleo(self, entrada):
        assert valor_contratadas(entrada) == parse_valor_cop(entrada)

    @pytest.mark.parametrize("entrada", CASOS)
    def test_tablero_coincide_con_el_nucleo(self, tablero, entrada):
        assert tablero._parse_valor(entrada) == parse_valor_cop(entrada)

    @pytest.mark.parametrize("entrada", CASOS)
    def test_el_respaldo_del_tablero_tambien_coincide(self, tablero, entrada):
        """Corriendo sin `app/` disponible el número no puede cambiar."""
        core = tablero._MONEDA_CORE
        tablero._MONEDA_CORE = None
        try:
            assert tablero._parse_valor(entrada) == parse_valor_cop(entrada)
        finally:
            tablero._MONEDA_CORE = core


class TestBugsQueSeCorrigieron:
    def test_tablero_ya_no_divide_por_mil(self, tablero):
        """El de gerencia: 950.000 se reportaba como 950 pesos."""
        assert tablero._parse_valor("950.000") == 950_000.0

    def test_tablero_respaldo_ya_no_divide_por_mil(self, tablero):
        core = tablero._MONEDA_CORE
        tablero._MONEDA_CORE = None
        try:
            assert tablero._parse_valor("950.000") == 950_000.0
        finally:
            tablero._MONEDA_CORE = core

    def test_apostrofo_de_miles_ya_no_da_cero(self):
        assert valor_excel("1'500.000") == 1_500_000.0
        assert valor_contratadas("1'500.000") == 1_500_000.0

    def test_cifra_en_palabras_ya_no_da_cero(self):
        assert valor_excel("850 millones") == 850_000_000.0
        assert valor_contratadas("850 millones") == 850_000_000.0

    def test_decimales_no_se_inflan_por_cien(self):
        """El defecto del conversor de SAVIA: borrar la coma pega los centavos."""
        assert parse_valor_cop("1.365,50") == 1365.5
        assert valor_excel("1.365,50") == 1365.5
        assert valor_contratadas("1.365,50") == 1365.5

    def test_punto_decimal_no_se_confunde_con_miles(self):
        """Un separador de miles SIEMPRE lleva 3 dígitos detrás. Con 1 o 2 es
        decimal: antes `20000.50` se leía como 2.000.050 y `0.99` como 99."""
        assert parse_valor_cop("20000.50") == 20000.5
        assert parse_valor_cop("0.99") == 0.99
        assert parse_valor_cop("7.70") == 7.7

    def test_los_formatos_colombianos_no_cambiaron(self):
        """La corrección anterior no puede tocar lo que ya funcionaba."""
        for entrada, esperado in [
            ("1.500", 1500.0),
            ("12.345", 12345.0),
            ("950.000", 950_000.0),
            ("1.500.000", 1_500_000.0),
            ("7.700", 7700.0),
            ("7.700,00", 7700.0),
            ("1.234.567,89", 1_234_567.89),
        ]:
            assert parse_valor_cop(entrada) == esperado, entrada


class TestSinCopiasNuevas:
    def test_los_modulos_de_tarifas_no_reimplementan_el_parser(self):
        """Si alguien vuelve a escribir la lógica a mano, esta prueba lo caza."""
        for ruta in (
            "app/services/tarifas_excel_parser.py",
            "app/api/routers/tarifas_contratadas.py",
        ):
            src = (RAIZ / ruta).read_text(encoding="utf-8")
            i = src.index("def _normalizar_valor")
            # Solo el cuerpo de esa función: hasta el siguiente `def` a nivel 0.
            resto = src[i + 1 :]
            j = resto.find("\ndef ")
            cuerpo = resto[: j if j > 0 else len(resto)]
            assert "parse_valor_cop" in cuerpo, f"{ruta} debe delegar en el núcleo"
            assert 'replace(",", ".")' not in cuerpo, f"{ruta} reimplementa el parser"
