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
