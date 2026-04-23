"""Tests del endpoint /tarifas-contratadas (Fase 1 — carga CSV + consulta)."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routers.tarifas_contratadas import _normalizar_valor
from app.database import Base


class TestNormalizarValor:
    def test_entero_sin_separadores(self):
        assert _normalizar_valor("20000") == 20000.0

    def test_con_puntos_miles(self):
        assert _normalizar_valor("1.500.000") == 1500000.0

    def test_con_comas_miles(self):
        assert _normalizar_valor("1,500,000") == 1500000.0

    def test_decimal_con_punto(self):
        assert _normalizar_valor("20000.50") == 20000.5

    def test_decimal_con_coma(self):
        assert _normalizar_valor("20000,50") == 20000.5

    def test_formato_us_miles_y_decimal(self):
        # 1,500.00 → 1500.00
        assert _normalizar_valor("1,500.00") == 1500.0

    def test_formato_europeo_miles_y_decimal(self):
        # 1.500,00 → 1500.00
        assert _normalizar_valor("1.500,00") == 1500.0

    def test_con_signo_peso(self):
        assert _normalizar_valor("$20,000") == 20000.0

    def test_string_vacio(self):
        assert _normalizar_valor("") == 0.0

    def test_invalido_devuelve_cero(self):
        assert _normalizar_valor("abc") == 0.0
