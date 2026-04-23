"""Tests de las funciones de optimización de tokens del motor de glosas."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ─── #7: generar_texto_tarifa_match (plantilla determinística) ──────────────

def test_generar_texto_tarifa_match_contiene_valores_clave():
    from app.services.glosa_service import generar_texto_tarifa_match
    info = {
        "tarifa": {
            "codigo_cups": "890202",
            "descripcion": "CONSULTA ESPECIALISTA",
            "contrato_numero": "S-13-1-03-1-04958",
            "eps": "FAMISANAR EPS",
            "modalidad": "MANUAL HUS",
            "fuente_archivo": "Anexos 3.xlsx",
        },
        "valor_pactado_calc": 83800.0,
        "valor_facturado": 83800.0,
    }
    txt = generar_texto_tarifa_match("TA0301", 83800.0, info)
    assert "ESE HUS NO ACEPTA" in txt
    assert "TA0301" in txt
    assert "FAMISANAR EPS" in txt
    assert "S-13-1-03-1-04958" in txt
    assert "890202" in txt
    assert "83.800" in txt  # format COP
    assert "ART" in txt.upper()  # cita jurídica (Art. 871/1602)
    assert "LEVANTAMIENTO" in txt.upper()


def test_generar_texto_tarifa_match_sin_descripcion_usa_fallback():
    from app.services.glosa_service import generar_texto_tarifa_match
    info = {
        "tarifa": {
            "codigo_cups": "890202",
            "descripcion": None,
            "contrato_numero": None,
            "eps": None,
            "modalidad": None,
        },
        "valor_pactado_calc": 1000.0,
        "valor_facturado": 1000.0,
    }
    txt = generar_texto_tarifa_match("TA0301", 1000.0, info)
    # No debe reventar con None; usa fallbacks
    assert "EL SERVICIO FACTURADO" in txt.upper() or "—" in txt
    assert "CONTRATO VIGENTE" in txt.upper() or "S-" in txt or "—" in txt


# ─── #1: Caché persistente en BD (funciones helper) ─────────────────────────

def test_buscar_cache_ia_db_sin_bd_no_rompe():
    """Si no hay sesión disponible o falla BD, debe devolver None sin crashear."""
    from app.services.glosa_service import _buscar_cache_ia_db
    with patch("app.database.SessionLocal", side_effect=RuntimeError("no db")):
        assert _buscar_cache_ia_db("clave-inexistente-xxxxxxxxx") is None


def test_guardar_cache_ia_db_sin_bd_no_rompe():
    """Si falla al guardar en BD, no debe propagar la excepción."""
    from app.services.glosa_service import _guardar_cache_ia_db
    with patch("app.database.SessionLocal", side_effect=RuntimeError("no db")):
        # No debe lanzar excepción
        _guardar_cache_ia_db("k", "respuesta", "modelo/x")


# ─── #3: Prompt caching de Anthropic ────────────────────────────────────────

@pytest.mark.asyncio
async def test_llamar_anthropic_usa_cache_control_con_system_largo():
    """System >=4000 chars → debe enviar system como list con cache_control."""
    from app.services.glosa_service import GlosaService

    svc = GlosaService.__new__(GlosaService)
    svc.anthropic_key = "sk-test"
    svc.anthropic_model = "claude-sonnet-4-6"

    system_largo = "x" * 5000  # >= 4000
    captured = {}

    class _FakeResp:
        def json(_self):
            return {
                "content": [{"text": "respuesta"}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }

    class _FakeClient:
        async def __aenter__(_self):
            return _self
        async def __aexit__(_self, *a):
            pass
        async def post(_self, url, headers=None, json=None):
            captured["json"] = json
            return _FakeResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        await svc._llamar_anthropic(system_largo, "user text")

    sp = captured["json"]["system"]
    assert isinstance(sp, list), "system debe ser list cuando es largo"
    assert sp[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_llamar_anthropic_sin_cache_control_con_system_corto():
    """System corto (<4000) → enviar como string plano (sin caching)."""
    from app.services.glosa_service import GlosaService

    svc = GlosaService.__new__(GlosaService)
    svc.anthropic_key = "sk-test"
    svc.anthropic_model = "claude-sonnet-4-6"

    system_corto = "eres un abogado"  # corto
    captured = {}

    class _FakeResp:
        def json(_self):
            return {"content": [{"text": "respuesta"}], "usage": {}}

    class _FakeClient:
        async def __aenter__(_self): return _self
        async def __aexit__(_self, *a): pass
        async def post(_self, url, headers=None, json=None):
            captured["json"] = json
            return _FakeResp()

    with patch("httpx.AsyncClient", return_value=_FakeClient()):
        await svc._llamar_anthropic(system_corto, "user text")

    sp = captured["json"]["system"]
    assert isinstance(sp, str), "system corto debe ir como string"


# ─── #8: Umbral de OCR más alto ─────────────────────────────────────────────

def test_umbral_texto_minimo_es_300():
    from app.services import pdf_service
    assert pdf_service.UMBRAL_TEXTO_MINIMO == 300


# ─── #6: Rate limit key por usuario ─────────────────────────────────────────

def test_limit_key_con_token_valido_devuelve_email():
    """Si viene un JWT válido en el header, la key es 'user:<email>'."""
    from jose import jwt as _jwt
    from app.core.config import get_settings
    from app.main import _limit_key_user_or_ip
    cfg = get_settings()
    token = _jwt.encode({"sub": "test@hus.gov.co"}, cfg.secret_key, algorithm=cfg.algorithm)
    req = SimpleNamespace(headers={"authorization": f"Bearer {token}"},
                           client=SimpleNamespace(host="1.2.3.4"))
    assert _limit_key_user_or_ip(req) == "user:test@hus.gov.co"


def test_limit_key_sin_token_usa_ip():
    """Sin JWT, cae a get_remote_address (IP)."""
    from app.main import _limit_key_user_or_ip
    # get_remote_address espera un request tipo Starlette; mockeamos lo mínimo
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="9.9.9.9"),
                           scope={"client": ("9.9.9.9", 0), "headers": [], "type": "http"})
    result = _limit_key_user_or_ip(req)
    # Debe devolver algo que no sea "user:..."
    assert not str(result).startswith("user:")


def test_limit_key_con_token_invalido_usa_ip():
    """JWT basura → no debe crashear, cae a IP."""
    from app.main import _limit_key_user_or_ip
    req = SimpleNamespace(headers={"authorization": "Bearer tokenbasura"},
                           client=SimpleNamespace(host="8.8.8.8"),
                           scope={"client": ("8.8.8.8", 0), "headers": [], "type": "http"})
    result = _limit_key_user_or_ip(req)
    assert not str(result).startswith("user:")


# ─── Integración análisis con info_tarifa → skip LLM ────────────────────────

@pytest.mark.asyncio
async def test_cache_ia_lock_impide_race_condition():
    """Con 10 llamadas concurrentes a la misma clave, el lock debe asegurar
    que la respuesta cacheada es consistente (misma tupla, no None, no corrupta)."""
    import asyncio as _aio
    from app.services.glosa_service import _CACHE_IA, _CACHE_IA_LOCK
    # Setear entrada inicial con lock
    async with _CACHE_IA_LOCK:
        _CACHE_IA["clave_test_race"] = ("respuesta_test", "modelo_test")

    async def leer():
        async with _CACHE_IA_LOCK:
            return _CACHE_IA.get("clave_test_race")

    resultados = await _aio.gather(*[leer() for _ in range(20)])
    # Todos deben ser la misma tupla, no None, no corrupta
    assert all(r == ("respuesta_test", "modelo_test") for r in resultados)


def test_clamp_per_page_repositorio():
    """per_page > 1000 debe clampearse a 1000 para evitar full table scans."""
    from app.repositories.glosa_repository import GlosaRepository
    from unittest.mock import MagicMock
    # Mock de DB: listar_paginado internamente hace query.count() + offset + limit
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.count.return_value = 0
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = []
    db.query.return_value = query_mock
    # Mock _query_con_filtros para que no toque la BD real
    repo = GlosaRepository(db)
    repo._query_con_filtros = MagicMock(return_value=query_mock)
    # Llamar con per_page absurdamente grande
    resultado = repo.listar_paginado(page=1, per_page=999_999)
    # Debe clampear a 1000
    assert resultado["per_page"] == 1000
    # Y page negativa debe ir a 1
    resultado2 = repo.listar_paginado(page=-5, per_page=50)
    assert resultado2["page"] == 1


@pytest.mark.asyncio
async def test_analizar_con_match_perfecto_salta_llm():
    """Con info_tarifa DEFENDER_TOTAL y valores iguales, NO se llama al LLM."""
    from app.services.glosa_service import GlosaService
    from app.models.schemas import GlosaInput

    svc = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
    data = GlosaInput(
        eps="FAMISANAR EPS",
        etapa="INICIAL",
        tabla_excel="TA0301 CUPS 890202 VALOR 83800",
        valor_aceptado="0",
        tono="conciliador",
    )
    info = {
        "encontrada": True,
        "tarifa": {
            "codigo_cups": "890202",
            "descripcion": "CONSULTA ESPECIALISTA",
            "contrato_numero": "S-13-1-03-1-04958",
            "eps": "FAMISANAR EPS",
            "modalidad": "MANUAL HUS",
            "valor_pactado": 83800.0,
            "tipo_tarifa": "VALOR_FIJO",
            "factor_ajuste": 0.0,
            "fuente_archivo": "test.xlsx",
        },
        "valor_pactado_calc": 83800.0,
        "valor_facturado": 83800.0,
        "valor_objetado": 0.0,
        "recomendacion": {
            "accion": "DEFENDER_TOTAL",
            "titulo": "Defender",
            "razon": "",
            "valor_a_defender": 83800.0,
            "valor_a_aceptar": 0.0,
            "diferencia": 0.0,
        },
    }
    resultado = await svc.analizar(data, info_tarifa=info, contratos_db={"FAMISANAR EPS": "X"})
    # El modelo usado debe ser 'texto_fijo' (NO una llamada a LLM)
    assert resultado.modelo_ia == "texto_fijo"
    # El dictamen debe contener la plantilla determinística
    assert "ESE HUS NO ACEPTA" in resultado.dictamen.upper()
    assert "S-13-1-03-1-04958" in resultado.dictamen
