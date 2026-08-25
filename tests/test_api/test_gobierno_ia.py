"""Gobierno de IA: el gasto se ve, por modelo, por usuario y con su caché.

Los datos existían llamada por llamada (ai_calls); esto prueba la vista
que los cuenta y quién puede verla.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import AICallRecord, UsuarioRecord


@pytest.fixture
def db_session():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _sembrar(db):
    db.add_all(
        [
            AICallRecord(
                proveedor="anthropic",
                modelo="claude-sonnet",
                latency_ms=2000,
                input_tokens=1000,
                cache_read_input_tokens=9000,
                output_tokens=800,
                cost_usd=0.05,
                glosa_id=87,
                user_email="yesid@hus.gov.co",
            ),
            AICallRecord(
                proveedor="groq",
                modelo="llama-3.3-70b",
                latency_ms=900,
                input_tokens=4000,
                cache_read_input_tokens=0,
                output_tokens=1200,
                cost_usd=0.002,
                glosa_id=87,
                user_email="ana@hus.gov.co",
            ),
            AICallRecord(
                proveedor="groq",
                modelo="llama-3.3-70b",
                latency_ms=1100,
                input_tokens=3000,
                output_tokens=900,
                cost_usd=0.001,
                glosa_id=91,
                user_email="yesid@hus.gov.co",
            ),
        ]
    )
    db.commit()


def _cliente(db_session, rol):
    from app.api.deps import get_usuario_actual
    from app.main import app

    u = UsuarioRecord(id=1, email="c@hus.gov.co", nombre="C", rol=rol, activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    return TestClient(app)


class TestResumen:
    def test_cuenta_gasto_modelos_usuarios_cache_y_glosas(self, db_session):
        from app.main import app

        _sembrar(db_session)
        with _cliente(db_session, "COORDINADOR") as c:
            r = c.get("/gobierno-ia/resumen")
        app.dependency_overrides.clear()

        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gasto"]["mes"]["llamadas"] == 3
        assert d["gasto"]["mes"]["costo_usd"] == pytest.approx(0.053, abs=0.001)

        modelos = {m["modelo"]: m for m in d["por_modelo"]}
        assert modelos["llama-3.3-70b"]["llamadas"] == 2
        assert modelos["claude-sonnet"]["costo_usd"] == pytest.approx(0.05)

        usuarios = {u["usuario"]: u for u in d["por_usuario"]}
        assert usuarios["yesid@hus.gov.co"]["llamadas"] == 2

        # 9.000 de caché sobre 17.000 totales de entrada ≈ 52.9%
        assert d["cache"]["porcentaje_cacheado"] == pytest.approx(52.9, abs=0.2)

        assert d["glosas_mas_caras"][0]["glosa_id"] == 87
        assert d["glosas_mas_caras"][0]["llamadas"] == 2

    def test_auditor_no_ve_el_gasto(self, db_session):
        from app.main import app

        with _cliente(db_session, "AUDITOR") as c:
            assert c.get("/gobierno-ia/resumen").status_code == 403
        app.dependency_overrides.clear()


class TestIAConoceSuGasto:
    async def test_la_tool_responde(self, db_session):
        from app.services import asistente_maestro as am

        assert any(t["name"] == "gobierno_ia" for t in am.TOOLS_ASISTENTE)
        _sembrar(db_session)
        d = json.loads(
            await am.execute_tool_asistente("gobierno_ia", {}, db=db_session, current_user=None)
        )
        assert d["gasto"]["mes"]["llamadas"] == 3


class TestPantalla:
    def test_existe_con_navegacion(self):
        from pathlib import Path

        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert 'id="p-gobierno-ia"' in html
        assert 'id="sn-gobierno-ia"' in html
        assert "function gobCargar" in html
        assert "expAbrirDesdeGob" in html  # de la glosa cara al expediente


class TestProbarProveedores:
    """La prueba de conexión nació del 04-08-2026: la única forma de saber
    si una clave nueva servía era analizar una glosa de verdad y ver si
    fallaba. Ahora se prueba en un clic, sin gastar una glosa."""

    def test_dice_cual_responde_y_cual_no(self, db_session, monkeypatch):
        from app.core.config import get_settings
        from app.main import app
        from app.services import glosa_service as gs

        cfg = get_settings()
        monkeypatch.setattr(cfg, "groq_api_key", "gsk_prueba", raising=False)
        monkeypatch.setattr(cfg, "anthropic_api_key", "sk-ant-prueba", raising=False)
        monkeypatch.setattr(cfg, "primary_ai", "groq", raising=False)

        async def _groq_ok(self, system, user, **kw):
            return ("LISTO", "llama-3.3-70b")

        async def _ant_falla(self, system, user, **kw):
            raise RuntimeError("Error code: 401 - invalid_api_key")

        monkeypatch.setattr(gs.GlosaService, "_llamar_groq_con_retry", _groq_ok)
        monkeypatch.setattr(gs.GlosaService, "_llamar_anthropic", _ant_falla)

        with _cliente(db_session, "COORDINADOR") as c:
            d = c.get("/gobierno-ia/probar-proveedores").json()
        app.dependency_overrides.clear()

        assert d["funciona"] is True
        assert "Todo listo" in d["veredicto"] and "GROQ" in d["veredicto"]
        por = {p["proveedor"]: p for p in d["proveedores"]}
        assert por["groq"]["estado"] == "OK" and por["groq"]["es_principal"] is True
        assert por["anthropic"]["estado"] == "FALLA"
        assert "inválida o vencida" in por["anthropic"]["detalle"]

    def test_sin_ninguno_avisa_que_no_va_a_funcionar(self, db_session, monkeypatch):
        from app.core.config import get_settings
        from app.main import app

        cfg = get_settings()
        monkeypatch.setattr(cfg, "groq_api_key", "", raising=False)
        monkeypatch.setattr(cfg, "anthropic_api_key", "", raising=False)

        with _cliente(db_session, "COORDINADOR") as c:
            d = c.get("/gobierno-ia/probar-proveedores").json()
        app.dependency_overrides.clear()

        assert d["funciona"] is False
        assert "no va a funcionar" in d["veredicto"]
        assert all(p["estado"] == "SIN CLAVE" for p in d["proveedores"])

    def test_el_auditor_no_prueba(self, db_session):
        from app.main import app

        with _cliente(db_session, "AUDITOR") as c:
            assert c.get("/gobierno-ia/probar-proveedores").status_code == 403
        app.dependency_overrides.clear()

    def test_el_boton_esta_en_la_pantalla(self):
        from pathlib import Path

        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "Probar proveedores de IA" in html
        assert "function gobProbar" in html
        assert "/gobierno-ia/probar-proveedores" in html
