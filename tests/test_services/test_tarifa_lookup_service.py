"""Tests del servicio de evaluación de tarifas pactadas."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.tarifa_lookup_service import (
    calcular_valor_pactado,
    evaluar_glosa_tarifa,
    formato_texto_banner,
)


def _tarifa(**kw):
    """Factory para TarifaContratadaRecord mockeado."""
    defaults = {
        "id": 1,
        "eps": "FAMISANAR EPS",
        "codigo_cups": "890202",
        "descripcion": "CONSULTA DE PRIMERA VEZ POR ESPECIALISTA",
        "contrato_numero": "S-13-1-03-1-04958",
        "valor_pactado": 83800.0,
        "tipo_tarifa": "VALOR_FIJO",
        "factor_ajuste": 0.0,
        "modalidad": "MANUAL HUS",
        "fuente_archivo": "fam.xlsx",
        "vigencia_desde": datetime(2026, 4, 15),
        "vigencia_hasta": datetime(2027, 4, 14),
        "activa": 1,
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestCalcularValorPactado:
    def test_valor_fijo(self):
        t = _tarifa(tipo_tarifa="VALOR_FIJO", valor_pactado=100_000)
        assert calcular_valor_pactado(t) == 100_000.0

    def test_soat_con_descuento_5pct(self):
        t = _tarifa(tipo_tarifa="SOAT_PORCENTAJE", factor_ajuste=-5.0, valor_pactado=0)
        # SOAT base = 100_000 → 100_000 × 0.95 = 95_000
        assert calcular_valor_pactado(t, valor_soat_base=100_000) == 95_000.0

    def test_soat_con_recargo_10pct(self):
        t = _tarifa(tipo_tarifa="SOAT_PORCENTAJE", factor_ajuste=10.0, valor_pactado=0)
        assert calcular_valor_pactado(t, valor_soat_base=100_000) == 110_000.0

    def test_soat_sin_base_devuelve_0(self):
        t = _tarifa(tipo_tarifa="SOAT_PORCENTAJE", factor_ajuste=-5.0, valor_pactado=0)
        # Sin valor_soat_base, no hay cómo calcular
        assert calcular_valor_pactado(t, valor_soat_base=0) == 0.0

    def test_none_tarifa(self):
        assert calcular_valor_pactado(None) == 0.0


class TestEvaluarGlosaTarifa:
    def _db_mock(self, tarifa):
        """Mock de sesión SQLAlchemy que devuelve `tarifa` en .first()."""
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = tarifa
        db.query.return_value = q
        return db

    def test_no_encontrada(self):
        db = self._db_mock(None)
        r = evaluar_glosa_tarifa(db, "FAMISANAR EPS", "999999",
                                  valor_facturado=100_000, valor_objetado=20_000)
        assert r["encontrada"] is False
        assert r["tarifa"] is None
        assert r["recomendacion"] is None

    def test_eps_vacia_no_encontrada(self):
        db = self._db_mock(_tarifa())
        r = evaluar_glosa_tarifa(db, "", "890202", valor_facturado=100, valor_objetado=0)
        assert r["encontrada"] is False

    def test_facturado_igual_pactado_defender_total(self):
        t = _tarifa(valor_pactado=83800.0)
        db = self._db_mock(t)
        r = evaluar_glosa_tarifa(db, "FAMISANAR EPS", "890202",
                                  valor_facturado=83800, valor_objetado=10_000)
        assert r["encontrada"]
        assert r["recomendacion"]["accion"] == "DEFENDER_TOTAL"
        assert r["valor_pactado_calc"] == 83800.0

    def test_facturado_mayor_al_pactado_aceptar_parcial(self):
        t = _tarifa(valor_pactado=83800.0)
        db = self._db_mock(t)
        # Hospital facturó 100_000, pactado es 83_800. Diferencia=16_200.
        # EPS objeta 20_000 → cabe la diferencia → aceptar parcial 16_200, defender 3_800
        r = evaluar_glosa_tarifa(db, "FAMISANAR EPS", "890202",
                                  valor_facturado=100_000, valor_objetado=20_000)
        assert r["encontrada"]
        rec = r["recomendacion"]
        assert rec["accion"] == "ACEPTAR_PARCIAL"
        assert rec["valor_a_aceptar"] == 16_200.0
        assert rec["valor_a_defender"] == 3_800.0

    def test_facturado_menor_al_pactado_defender(self):
        t = _tarifa(valor_pactado=83800.0)
        db = self._db_mock(t)
        r = evaluar_glosa_tarifa(db, "FAMISANAR EPS", "890202",
                                  valor_facturado=70_000, valor_objetado=10_000)
        assert r["recomendacion"]["accion"] == "DEFENDER_TOTAL"
        assert r["recomendacion"]["valor_a_defender"] == 70_000.0

    def test_diferencia_excede_objetado_revisar(self):
        t = _tarifa(valor_pactado=50_000.0)
        db = self._db_mock(t)
        # Diferencia facturado-pactado = 100_000 - 50_000 = 50_000.
        # EPS solo objeta 20_000 → no cabe → REVISAR
        r = evaluar_glosa_tarifa(db, "FAMISANAR EPS", "890202",
                                  valor_facturado=100_000, valor_objetado=20_000)
        assert r["recomendacion"]["accion"] == "REVISAR"

    def test_soat_porcentaje_calcula_pactado(self):
        t = _tarifa(tipo_tarifa="SOAT_PORCENTAJE", factor_ajuste=-5.0,
                     valor_pactado=0)
        db = self._db_mock(t)
        r = evaluar_glosa_tarifa(db, "FAMISANAR EPS", "890202",
                                  valor_facturado=95_000, valor_objetado=10_000,
                                  valor_soat_base=100_000)
        assert r["valor_pactado_calc"] == 95_000.0
        # facturado==pactado → DEFENDER
        assert r["recomendacion"]["accion"] == "DEFENDER_TOTAL"


class TestFormatoTextoBanner:
    def test_sin_tarifa_vacio(self):
        assert formato_texto_banner({"encontrada": False}) == ""

    def test_info_none_vacio(self):
        assert formato_texto_banner(None) == ""

    def test_contiene_datos_clave(self):
        info = {
            "encontrada": True,
            "tarifa": {
                "codigo_cups": "890202",
                "descripcion": "CONSULTA",
                "eps": "FAMISANAR EPS",
                "contrato_numero": "S-13-1-03-1-04958",
                "modalidad": "MANUAL HUS",
                "tipo_tarifa": "VALOR_FIJO",
                "valor_pactado": 83800.0,
                "factor_ajuste": 0.0,
            },
            "valor_facturado": 83800.0,
            "valor_objetado": 10_000.0,
            "valor_pactado_calc": 83800.0,
            "recomendacion": {
                "accion": "DEFENDER_TOTAL",
                "titulo": "✅ Defender 100%",
                "razon": "Coincide pactada",
            },
        }
        txt = formato_texto_banner(info)
        assert "890202" in txt
        assert "S-13-1-03-1-04958" in txt
        assert "83,800" in txt
        assert "Defender 100%" in txt
        assert "Art. 1602" in txt  # cita jurídica

    def test_soat_porcentaje_muestra_factor(self):
        info = {
            "encontrada": True,
            "tarifa": {
                "codigo_cups": "010101",
                "descripcion": "PUNCION",
                "eps": "FAMISANAR EPS",
                "contrato_numero": "X-123",
                "modalidad": "SOAT UVB",
                "tipo_tarifa": "SOAT_PORCENTAJE",
                "factor_ajuste": -5.0,
                "valor_pactado": 0,
            },
            "valor_facturado": 95_000,
            "valor_objetado": 10_000,
            "valor_pactado_calc": 95_000,
            "recomendacion": {
                "accion": "DEFENDER_TOTAL",
                "titulo": "Defender",
                "razon": "OK",
            },
        }
        txt = formato_texto_banner(info)
        assert "SOAT -5%" in txt or "SOAT - 5%" in txt or "-5" in txt
