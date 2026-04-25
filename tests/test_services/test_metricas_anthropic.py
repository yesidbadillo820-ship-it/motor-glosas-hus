"""Tests de las métricas de costo/latencia Anthropic (R54 P3)."""
from __future__ import annotations

import logging

from app.services.glosa_service import (
    _calcular_costo_anthropic_usd,
    _log_metricas_anthropic,
)


class TestCalcularCostoAnthropic:
    def test_sin_cache_sonnet(self):
        """Tarifas standard Sonnet 4.6: $3 input, $15 output por MTok."""
        usage = {"input_tokens": 1_000_000, "output_tokens": 0}
        c = _calcular_costo_anthropic_usd(usage, "claude-sonnet-4-6")
        assert abs(c - 3.0) < 0.001

    def test_solo_output(self):
        usage = {"input_tokens": 0, "output_tokens": 1_000_000}
        c = _calcular_costo_anthropic_usd(usage, "claude-sonnet-4-6")
        assert abs(c - 15.0) < 0.001

    def test_cache_read_es_10_pct(self):
        """Cache read debe costar 10% del input normal."""
        usage = {"cache_read_input_tokens": 1_000_000, "input_tokens": 0, "output_tokens": 0}
        c = _calcular_costo_anthropic_usd(usage, "claude-sonnet-4-6")
        assert abs(c - 0.30) < 0.001  # 3.0 × 10%

    def test_cache_write_1h_es_2x(self):
        """Cache write con TTL=1h debe costar 2× del input normal."""
        usage = {"cache_creation_input_tokens": 1_000_000, "input_tokens": 0, "output_tokens": 0}
        c = _calcular_costo_anthropic_usd(usage, "claude-sonnet-4-6")
        assert abs(c - 6.0) < 0.001  # 3.0 × 2

    def test_modelo_desconocido_usa_default(self):
        usage = {"input_tokens": 1000, "output_tokens": 500}
        c = _calcular_costo_anthropic_usd(usage, "modelo-inexistente-xxx")
        # default = sonnet-like (3 / 15)
        assert c > 0
        # Costo: (1000×3 + 500×15) / 1M = 0.0105
        assert abs(c - 0.0105) < 0.001

    def test_usage_invalido_retorna_cero(self):
        assert _calcular_costo_anthropic_usd(None, "claude-sonnet-4-6") == 0.0
        assert _calcular_costo_anthropic_usd("string", "claude-sonnet-4-6") == 0.0

    def test_haiku_es_mas_barato_que_sonnet(self):
        usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        sonnet = _calcular_costo_anthropic_usd(usage, "claude-sonnet-4-6")
        haiku = _calcular_costo_anthropic_usd(usage, "claude-haiku-4-5-20251001")
        assert haiku < sonnet


class TestLogMetricas:
    def test_log_emite_estructurado(self, caplog):
        caplog.set_level(logging.INFO, logger="motor_glosas")
        usage = {"input_tokens": 100, "output_tokens": 50}
        _log_metricas_anthropic(usage, "claude-sonnet-4-6", 1234)
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "ANTHROPIC-CALL" in msgs
        assert "latency_ms=1234" in msgs
        assert "claude-sonnet-4-6" in msgs
        assert "cost_usd=$" in msgs

    def test_log_calcula_cache_hit_pct(self, caplog):
        caplog.set_level(logging.INFO, logger="motor_glosas")
        # 100 tokens normales + 900 cache_read = 90% cache hit
        usage = {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 50}
        _log_metricas_anthropic(usage, "claude-sonnet-4-6", 800)
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "cache_hit_pct=90.0" in msgs

    def test_log_no_explota_con_usage_invalido(self, caplog):
        caplog.set_level(logging.INFO, logger="motor_glosas")
        # No debe lanzar exception
        _log_metricas_anthropic(None, "x", 0)
        _log_metricas_anthropic("not-a-dict", "x", 0)
