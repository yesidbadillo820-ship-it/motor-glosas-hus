"""Tests del adapter Quality Gate ↔ GlosaService."""

from __future__ import annotations

import pytest

from app.services.quality_gate import QualityGateResult
from app.services.quality_gate_adapter import (
    debe_usar_quality_gate,
    ejecutar_con_quality_gate,
    es_quality_gate_activo,
    porcentaje_rollout,
)


class _SpyService:
    """Stub de GlosaService que registra cada llamada a _llamar_ia."""

    anthropic_key = "key"
    anthropic_model = "claude-sonnet-4-5"
    groq = "client"
    gemini = None

    def __init__(self, respuestas=None):
        self.llamadas = []
        # Lista de respuestas a devolver en orden; la última se repite.
        self._respuestas = respuestas or ["<argumento>OK</argumento>"]

    async def _llamar_ia(
        self, system, user, eps="", codigo="", modelo_override=None, bypass_cache=False
    ):
        self.llamadas.append({"modelo_override": modelo_override, "bypass_cache": bypass_cache})
        idx = min(len(self.llamadas) - 1, len(self._respuestas) - 1)
        return (self._respuestas[idx], "modelo-real")

    def _xml(self, tag, text, default=""):
        open_t, close_t = f"<{tag}>", f"</{tag}>"
        if open_t in text and close_t in text:
            return text.split(open_t, 1)[1].split(close_t, 1)[0]
        return default


_TEXTO_GLOSA_VALIDO = (
    "TA0201 - Mayor valor cobrado en consulta especializada "
    "por valor objetado de $7.700,00 según factura electrónica"
)


class TestGeneradorRegeneraDeVerdad:
    """Regresión auditoría jun-2026 P1 #2: la regeneración del QG era un
    no-op porque el generador ignoraba `modelo` y no bypaseaba el caché —
    los intentos 2 y 3 devolvían la misma respuesta cacheada rechazada."""

    async def _capturar_generador(self, monkeypatch, servicio):
        captura = {}

        async def fake_orchestrator(**kwargs):
            captura["generador"] = kwargs["generador"]
            captura["modelos_fallback"] = kwargs["modelos_fallback"]
            return QualityGateResult(estado="APROBADO", dictamen_final="x")

        monkeypatch.setattr(
            "app.services.quality_gate_adapter.ejecutar_quality_gate",
            fake_orchestrator,
        )
        await ejecutar_con_quality_gate(
            servicio=servicio,
            eps="FAMISANAR EPS",
            codigo_glosa="TA0201",
            valor_objetado="$ 7.700,00",
            texto_glosa=_TEXTO_GLOSA_VALIDO,
            system_prompt="system",
            user_prompt="user",
            proveedores_disponibles={"groq", "anthropic", "gemini"},
        )
        return captura

    @pytest.mark.asyncio
    async def test_bypass_cache_solo_desde_el_segundo_intento(self, monkeypatch):
        spy = _SpyService()
        captura = await self._capturar_generador(monkeypatch, spy)
        gen = captura["generador"]

        await gen(modelo="groq")
        await gen(modelo="groq")
        await gen(modelo="groq")

        # Intento 1 puede usar caché; 2 y 3 DEBEN bypassearla.
        assert [c["bypass_cache"] for c in spy.llamadas] == [False, True, True]

    @pytest.mark.asyncio
    async def test_modelo_anthropic_se_mapea_a_modelo_override(self, monkeypatch):
        spy = _SpyService()
        captura = await self._capturar_generador(monkeypatch, spy)
        gen = captura["generador"]

        await gen(modelo="groq")
        await gen(modelo="anthropic")
        await gen(modelo="gemini")

        overrides = [c["modelo_override"] for c in spy.llamadas]
        # groq/gemini no son forzables vía modelo_override (ese parámetro
        # siempre enruta a Anthropic); anthropic sí.
        assert overrides == [None, "claude-sonnet-4-5", None]

    @pytest.mark.asyncio
    async def test_sin_anthropic_key_no_fuerza_override(self, monkeypatch):
        spy = _SpyService()
        spy.anthropic_key = None
        captura = await self._capturar_generador(monkeypatch, spy)
        gen = captura["generador"]

        await gen(modelo="anthropic")

        assert spy.llamadas[0]["modelo_override"] is None

    @pytest.mark.asyncio
    async def test_e2e_regeneracion_recupera_dictamen(self):
        """End-to-end con el orchestrator REAL: el intento 1 devuelve un
        dictamen defectuoso (simula caché rancia); el intento 2, ya con
        bypass_cache=True, devuelve uno bueno → APROBADO con 1 regeneración.
        Antes del fix, el intento 2 repetía la respuesta defectuosa."""
        dictamen_bueno = (
            "<argumento>"
            + "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE MAYOR VALOR. " * 5
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO INTEGRO.</argumento>"
        )
        spy = _SpyService(respuestas=["<argumento>corto</argumento>", dictamen_bueno])

        resultado = await ejecutar_con_quality_gate(
            servicio=spy,
            eps="FAMISANAR EPS",
            codigo_glosa="TA0201",
            valor_objetado="$ 7.700,00",
            texto_glosa=_TEXTO_GLOSA_VALIDO,
            system_prompt="system",
            user_prompt="user",
            proveedores_disponibles={"groq", "anthropic"},
        )

        assert resultado.estado == "APROBADO"
        assert resultado.n_regeneraciones >= 1
        assert "SE SOLICITA EL LEVANTAMIENTO" in resultado.dictamen_final
        # La 2ª llamada al proveedor fue SIN caché — el corazón del fix.
        assert spy.llamadas[1]["bypass_cache"] is True


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
