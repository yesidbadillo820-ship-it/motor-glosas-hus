"""Cadena de fallback INTERNA de Groq (decisión 12-jun-2026).

GlosaService._llamar_groq_con_retry debe agotar la cadena de modelos Groq

    openai/gpt-oss-120b → qwen/qwen3-32b → llama-3.3-70b-versatile

antes de propagar la excepción (y que recién ahí _llamar_ia caiga a
Anthropic). Reglas:
  - 429/rate-limit con modelos pendientes → saltar de inmediato al
    siguiente modelo (buckets de rate limit por modelo, sin backoff).
  - Error transitorio (timeout/conexión) → retry exponencial sobre el
    MISMO modelo, luego el siguiente.
  - El log [GROQ-CALL]/[GROQ-FALLBACK] deja claro QUÉ modelo respondió.
"""

import logging
import uuid

import pytest

from app.services.glosa_service import GlosaService

PRIMARIO = "meta-llama/llama-4-scout-17b-16e-instruct"
FALLBACK_1 = "openai/gpt-oss-120b"
FALLBACK_2 = "qwen/qwen3-32b"
FALLBACK_3 = "llama-3.3-70b-versatile"

RESPUESTA_OK = "<paciente>JUAN PEREZ</paciente><argumento>NO SE ACEPTA LA GLOSA</argumento>"


def _err_429() -> Exception:
    """Mismo formato de mensaje que groq.RateLimitError stringificado."""
    return RuntimeError("Error code: 429 - Rate limit reached for model, please try again")


def _err_deprecado() -> Exception:
    """Error NO reintentable (p.ej. modelo dado de baja por Groq)."""
    return RuntimeError("Error code: 400 - The model has been decommissioned")


# ─── Fakes del cliente Groq (chat.completions.create) ──────────────────────


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)
        self.finish_reason = "stop"


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    """Comportamiento por modelo: str (respuesta), Exception, o lista de
    acciones que se consume en orden (para simular 429 → luego éxito)."""

    def __init__(self, por_modelo: dict):
        self.por_modelo = por_modelo
        self.llamadas: list[str] = []

    async def create(self, **kwargs):
        modelo = kwargs["model"]
        self.llamadas.append(modelo)
        accion = self.por_modelo[modelo]
        if isinstance(accion, list):
            accion = accion.pop(0)
        if isinstance(accion, Exception):
            raise accion
        return _FakeResp(accion)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeGroq:
    def __init__(self, por_modelo: dict):
        self.chat = _FakeChat(_FakeCompletions(por_modelo))

    @property
    def llamadas(self) -> list[str]:
        return self.chat.completions.llamadas


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def svc_factory(monkeypatch):
    """GlosaService con defaults de producción y sin keys reales del entorno."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def _crear(**kwargs) -> GlosaService:
        defaults = {"groq_api_key": "gsk_test", "anthropic_api_key": None, "primary_ai": "groq"}
        defaults.update(kwargs)
        return GlosaService(**defaults)

    return _crear


@pytest.fixture
def esperas(monkeypatch):
    """Anula el backoff (asyncio.sleep) y registra las esperas pedidas."""
    registradas: list[float] = []

    async def _sleep_instantaneo(segundos):
        registradas.append(segundos)

    monkeypatch.setattr("app.services.glosa_service.asyncio.sleep", _sleep_instantaneo)
    return registradas


@pytest.fixture
def sin_cache_db(monkeypatch):
    """Aísla _llamar_ia de la BD real (caché persistente ai_cache)."""
    monkeypatch.setattr("app.services.glosa_service._buscar_cache_ia_db", lambda clave: None)
    monkeypatch.setattr("app.services.glosa_service._guardar_cache_ia_db", lambda *a, **k: None)


def _user_unico() -> str:
    """Prompt único por test → clave de caché en memoria nunca colisiona."""
    return f"GLOSA TA0201 caso {uuid.uuid4()}"


# ─── Cadena de modelos ──────────────────────────────────────────────────────


class TestCadenaModelos:
    def test_orden_default_es_cadena_de_4(self, svc_factory):
        svc = svc_factory()
        assert svc._modelos_groq() == [PRIMARIO, FALLBACK_1, FALLBACK_2, FALLBACK_3]

    def test_defaults_del_constructor(self, svc_factory):
        svc = svc_factory()
        assert svc.groq_model == PRIMARIO
        assert svc.groq_model_fallback_1 == FALLBACK_1
        assert svc.groq_model_fallback_2 == FALLBACK_2
        assert svc.groq_model_fallback_3 == FALLBACK_3

    def test_override_que_coincide_con_fallback_no_duplica(self, svc_factory):
        # GROQ_MODEL=llama-3.3-70b-versatile (override del usuario) — el
        # mismo modelo no debe intentarse dos veces.
        svc = svc_factory(groq_model=FALLBACK_3)
        assert svc._modelos_groq() == [FALLBACK_3, FALLBACK_1, FALLBACK_2]

    def test_override_total_repetido_queda_un_solo_modelo(self, svc_factory):
        svc = svc_factory(
            groq_model="modelo-x",
            groq_model_fallback_1="modelo-x",
            groq_model_fallback_2="modelo-x",
            groq_model_fallback_3="modelo-x",
        )
        assert svc._modelos_groq() == ["modelo-x"]


# ─── 429 / rate limit ───────────────────────────────────────────────────────


class TestRateLimitPasaAlSiguienteModelo:
    @pytest.mark.asyncio
    async def test_429_en_primario_responde_fallback_1(self, svc_factory, esperas):
        svc = svc_factory()
        fake = _FakeGroq({PRIMARIO: _err_429(), FALLBACK_1: RESPUESTA_OK})
        svc.groq = fake

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert content == RESPUESTA_OK
        assert modelo == f"groq/{FALLBACK_1}"
        assert fake.llamadas == [PRIMARIO, FALLBACK_1]
        # El salto por rate limit es inmediato: NO quema backoff.
        assert esperas == []

    @pytest.mark.asyncio
    async def test_429_en_dos_primeros_llega_al_tercero(self, svc_factory, esperas):
        svc = svc_factory()
        fake = _FakeGroq({PRIMARIO: _err_429(), FALLBACK_1: _err_429(), FALLBACK_2: RESPUESTA_OK})
        svc.groq = fake

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert modelo == f"groq/{FALLBACK_2}"
        assert fake.llamadas == [PRIMARIO, FALLBACK_1, FALLBACK_2]
        assert esperas == []

    @pytest.mark.asyncio
    async def test_todos_429_propaga_excepcion_tras_agotar_cadena(self, svc_factory, esperas):
        svc = svc_factory()
        fake = _FakeGroq({m: _err_429() for m in (PRIMARIO, FALLBACK_1, FALLBACK_2, FALLBACK_3)})
        svc.groq = fake

        with pytest.raises(Exception, match="429"):
            await svc._llamar_groq_con_retry("sys", "user", max_intentos=1)

        # Probó los 4 modelos (sin duplicados) antes de rendirse.
        assert fake.llamadas == [PRIMARIO, FALLBACK_1, FALLBACK_2, FALLBACK_3]

    @pytest.mark.asyncio
    async def test_429_en_ultimo_modelo_si_usa_backoff(self, svc_factory, esperas):
        # En el ÚLTIMO modelo ya no hay adónde saltar dentro de Groq: el 429
        # se trata como reintentable clásico (backoff) antes de propagar.
        svc = svc_factory()
        fake = _FakeGroq(
            {
                PRIMARIO: _err_429(),
                FALLBACK_1: _err_429(),
                FALLBACK_2: _err_429(),
                FALLBACK_3: [_err_429(), RESPUESTA_OK],
            }
        )
        svc.groq = fake

        content, modelo = await svc._llamar_groq_con_retry("sys", "user", max_intentos=2)

        assert modelo == f"groq/{FALLBACK_3}"
        assert fake.llamadas == [
            PRIMARIO,
            FALLBACK_1,
            FALLBACK_2,
            FALLBACK_3,
            FALLBACK_3,
        ]
        assert esperas == [1]  # un solo backoff, en el último modelo


# ─── Errores no-rate-limit ──────────────────────────────────────────────────


class TestOtrosErrores:
    @pytest.mark.asyncio
    async def test_modelo_deprecado_pasa_al_siguiente_sin_backoff(self, svc_factory, esperas):
        # Groq da de baja modelos sin mucho aviso: un 400 "decommissioned"
        # en el primario NO debe tumbar el dictamen ni saltar a Anthropic.
        svc = svc_factory()
        fake = _FakeGroq({PRIMARIO: _err_deprecado(), FALLBACK_1: RESPUESTA_OK})
        svc.groq = fake

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert modelo == f"groq/{FALLBACK_1}"
        assert fake.llamadas == [PRIMARIO, FALLBACK_1]
        assert esperas == []

    @pytest.mark.asyncio
    async def test_timeout_reintenta_el_mismo_modelo_antes_de_caer(self, svc_factory, esperas):
        # Error transitorio ≠ rate limit: el retry exponencial sigue siendo
        # sobre el MISMO modelo (presupuesto max_intentos por modelo).
        svc = svc_factory()
        fake = _FakeGroq({PRIMARIO: [RuntimeError("connection timeout"), RESPUESTA_OK]})
        svc.groq = fake

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert modelo == f"groq/{PRIMARIO}"
        assert fake.llamadas == [PRIMARIO, PRIMARIO]
        assert esperas == [1]

    @pytest.mark.asyncio
    async def test_content_vacio_pasa_al_siguiente_modelo(self, svc_factory, esperas):
        # gpt-oss devolviendo content vacío era el motivo histórico para
        # preferir llama; con la cadena, un vacío cae al siguiente modelo.
        svc = svc_factory()
        fake = _FakeGroq({PRIMARIO: "", FALLBACK_1: RESPUESTA_OK})
        svc.groq = fake

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert content == RESPUESTA_OK
        assert modelo == f"groq/{FALLBACK_1}"
        assert fake.llamadas == [PRIMARIO, FALLBACK_1]


# ─── Logs ───────────────────────────────────────────────────────────────────


class TestLogsModeloReal:
    @pytest.mark.asyncio
    async def test_log_indica_modelo_que_respondio_y_fallback(self, svc_factory, esperas, caplog):
        caplog.set_level(logging.INFO, logger="motor_glosas")
        svc = svc_factory()
        svc.groq = _FakeGroq({PRIMARIO: _err_429(), FALLBACK_1: RESPUESTA_OK})

        await svc._llamar_groq_con_retry("sys", "user")

        mensajes = " | ".join(r.getMessage() for r in caplog.records)
        # El modelo REAL que respondió queda parseable (no solo "groq").
        assert f"[GROQ-CALL] model={FALLBACK_1}" in mensajes
        assert "latency_ms=" in mensajes
        # Y el salto de la cadena queda registrado con el modelo agotado.
        assert f"[GROQ-FALLBACK] model={PRIMARIO}" in mensajes
        assert FALLBACK_1 in mensajes

    @pytest.mark.asyncio
    async def test_etiqueta_devuelta_incluye_modelo_real(self, svc_factory, esperas):
        # La etiqueta groq/<modelo> alimenta modelo_ia en BD y el caché.
        svc = svc_factory()
        svc.groq = _FakeGroq({PRIMARIO: RESPUESTA_OK})

        _, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert modelo == f"groq/{PRIMARIO}"


# ─── Integración con _llamar_ia (no saltar a Anthropic prematuramente) ─────


class TestLlamarIaRespetaCadenaGroq:
    @pytest.mark.asyncio
    async def test_429_intermedio_no_toca_anthropic(
        self, svc_factory, esperas, sin_cache_db, monkeypatch
    ):
        svc = svc_factory(anthropic_api_key="sk-ant-test")
        fake = _FakeGroq({PRIMARIO: _err_429(), FALLBACK_1: RESPUESTA_OK})
        svc.groq = fake

        llamadas_anthropic: list[int] = []

        async def _anthropic_espia(system, user, modelo_override=None, temperature_override=None):
            llamadas_anthropic.append(1)
            return ("NO DEBERIA LLEGAR AQUI", "claude-sonnet-4-6")

        monkeypatch.setattr(svc, "_llamar_anthropic", _anthropic_espia)

        content, modelo = await svc._llamar_ia("sys", _user_unico())

        assert modelo == f"groq/{FALLBACK_1}"
        assert llamadas_anthropic == []  # Anthropic NO se tocó
        assert fake.llamadas == [PRIMARIO, FALLBACK_1]

    @pytest.mark.asyncio
    async def test_groq_agotado_recien_ahi_cae_a_anthropic(
        self, svc_factory, esperas, sin_cache_db, monkeypatch
    ):
        svc = svc_factory(anthropic_api_key="sk-ant-test")
        fake = _FakeGroq({m: _err_429() for m in (PRIMARIO, FALLBACK_1, FALLBACK_2, FALLBACK_3)})
        svc.groq = fake

        async def _anthropic_ok(system, user, modelo_override=None, temperature_override=None):
            return ("RESPUESTA DE CLAUDE", "claude-sonnet-4-6")

        monkeypatch.setattr(svc, "_llamar_anthropic", _anthropic_ok)

        content, modelo = await svc._llamar_ia("sys", _user_unico())

        assert modelo == "claude-sonnet-4-6"
        # Los 4 modelos Groq se intentaron en orden antes de Claude
        # (el último además con sus retries de backoff).
        assert fake.llamadas[:4] == [PRIMARIO, FALLBACK_1, FALLBACK_2, FALLBACK_3]
        assert set(fake.llamadas[4:]) <= {FALLBACK_3}
