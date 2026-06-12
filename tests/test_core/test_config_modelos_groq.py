"""Defaults y overrides por env de los modelos Groq.

Decisión 12-jun-2026 (benchmarks GPQA/MMLU de artificialanalysis.ai +
deprecaciones de Groq): la cadena de modelos Groq quedó en

    openai/gpt-oss-120b (primario) → qwen/qwen3-32b (fallback 1)
    → llama-3.3-70b-versatile (fallback 2)

Ver el comentario completo en app/core/config.py y la aplicación de la
cadena en GlosaService._llamar_groq_con_retry.
"""

from app.core.config import Settings, get_settings

_ENVS_GROQ = ("GROQ_MODEL", "GROQ_MODEL_FALLBACK_1", "GROQ_MODEL_FALLBACK_2")


def _settings_limpio(monkeypatch) -> Settings:
    """Settings sin interferencia de env vars del runner ni del .env local."""
    for var in _ENVS_GROQ:
        monkeypatch.delenv(var, raising=False)
    return Settings(_env_file=None)


class TestDefaultsModelosGroq:
    """Los 3 campos existen y traen la cadena del 12-jun-2026."""

    def test_primario_es_gpt_oss_120b(self, monkeypatch):
        s = _settings_limpio(monkeypatch)
        assert s.groq_model == "openai/gpt-oss-120b"

    def test_primario_ya_no_es_llama_33(self, monkeypatch):
        # El default viejo (llama-3.3-70b-versatile) pasó a ser el ÚLTIMO
        # recurso de la cadena, no el primario.
        s = _settings_limpio(monkeypatch)
        assert s.groq_model != "llama-3.3-70b-versatile"

    def test_fallback_1_es_qwen3_32b(self, monkeypatch):
        s = _settings_limpio(monkeypatch)
        assert s.groq_model_fallback_1 == "qwen/qwen3-32b"

    def test_fallback_2_es_llama_33(self, monkeypatch):
        s = _settings_limpio(monkeypatch)
        assert s.groq_model_fallback_2 == "llama-3.3-70b-versatile"

    def test_cadena_sin_duplicados_por_default(self, monkeypatch):
        s = _settings_limpio(monkeypatch)
        cadena = [s.groq_model, s.groq_model_fallback_1, s.groq_model_fallback_2]
        assert len(cadena) == len(set(cadena))


class TestOverridePorEnv:
    """GROQ_MODEL sigue funcionando y los fallbacks también son env-overridables."""

    def test_groq_model_respeta_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_MODEL", "modelo-custom-x")
        assert Settings(_env_file=None).groq_model == "modelo-custom-x"

    def test_fallback_1_respeta_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_MODEL_FALLBACK_1", "fb1-custom")
        assert Settings(_env_file=None).groq_model_fallback_1 == "fb1-custom"

    def test_fallback_2_respeta_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_MODEL_FALLBACK_2", "fb2-custom")
        assert Settings(_env_file=None).groq_model_fallback_2 == "fb2-custom"

    def test_get_settings_propaga_override(self, monkeypatch):
        monkeypatch.setenv("GROQ_MODEL", "modelo-via-get-settings")
        get_settings.cache_clear()
        try:
            assert get_settings().groq_model == "modelo-via-get-settings"
        finally:
            # No dejar cacheado un Settings construido con el env del test.
            get_settings.cache_clear()
