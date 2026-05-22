"""Tests del adapter Quality Gate ↔ GlosaService."""

from __future__ import annotations

from app.services.quality_gate_adapter import (
    debe_usar_quality_gate,
    es_quality_gate_activo,
    porcentaje_rollout,
)


class TestFlagsEnv:
    def test_inactivo_por_defecto(self, monkeypatch):
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        assert not es_quality_gate_activo()

    def test_activo_con_1(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        assert es_quality_gate_activo()

    def test_activo_con_true(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "true")
        assert es_quality_gate_activo()

    def test_inactivo_con_0(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "0")
        assert not es_quality_gate_activo()


class TestRollout:
    def test_default_100_pct(self, monkeypatch):
        monkeypatch.delenv("QUALITY_GATE_ROLLOUT_PCT", raising=False)
        assert porcentaje_rollout() == 100

    def test_clamp_min(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "-50")
        assert porcentaje_rollout() == 0

    def test_clamp_max(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "200")
        assert porcentaje_rollout() == 100

    def test_invalido_default(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "abc")
        assert porcentaje_rollout() == 100


class TestDebeUsarQualityGate:
    def test_off_global(self, monkeypatch):
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        for i in range(10):
            assert not debe_usar_quality_gate(glosa_id=i)

    def test_on_100pct(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "100")
        for i in range(20):
            assert debe_usar_quality_gate(glosa_id=i)

    def test_canary_10pct_sticky(self, monkeypatch):
        """Con 10% rollout y sticky por glosa_id, las glosas 0-9 deben pasar
        y las 10-19 no (decisión determinística por % módulo)."""
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "10")
        # ids 0-9 (< 10) pasan
        for i in range(10):
            assert debe_usar_quality_gate(glosa_id=i)
        # ids 10-19 (>= 10) no
        for i in range(10, 20):
            assert not debe_usar_quality_gate(glosa_id=i)

    def test_0pct_nadie_pasa(self, monkeypatch):
        monkeypatch.setenv("QUALITY_GATE_ENABLED", "1")
        monkeypatch.setenv("QUALITY_GATE_ROLLOUT_PCT", "0")
        for i in range(20):
            assert not debe_usar_quality_gate(glosa_id=i)
