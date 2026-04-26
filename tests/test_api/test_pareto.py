"""Tests del endpoint GET /glosas/stats/concentracion-pareto (R113 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def usuario():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, eps, valor):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestPareto:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/concentracion-pareto")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_eps"] == 0
        assert d["valor_total"] == 0
        assert d["gini_coefficient"] == 0.0
        assert d["top_eps_concentracion"] == []

    def test_distribucion_uniforme_gini_bajo(self, client, db_session):
        # 5 EPS con valores iguales → Gini cercano a 0
        for i in range(5):
            _seed(db_session, f"EPS{i}", 10000)
        r = client.get("/glosas/stats/concentracion-pareto")
        d = r.json()
        assert d["total_eps"] == 5
        assert d["gini_coefficient"] < 0.1  # casi-perfectamente igual

    def test_distribucion_concentrada_gini_alto(self, client, db_session):
        # 1 EPS con todo el valor → Gini cercano a 1
        _seed(db_session, "DOMINANTE", 1_000_000)
        for i in range(9):
            _seed(db_session, f"EPS{i}", 1)  # casi nada
        r = client.get("/glosas/stats/concentracion-pareto")
        d = r.json()
        assert d["gini_coefficient"] > 0.8

    def test_eps_para_80_pct(self, client, db_session):
        # 1 EPS = 80% + 4 EPS = 5% cada
        _seed(db_session, "BIG", 800)
        for i in range(4):
            _seed(db_session, f"S{i}", 50)
        r = client.get("/glosas/stats/concentracion-pareto")
        d = r.json()
        # 1 sola EPS aporta el 80%
        assert d["eps_para_80_pct"] == 1

    def test_top_concentracion_acumulado(self, client, db_session):
        _seed(db_session, "A", 50)
        _seed(db_session, "B", 30)
        _seed(db_session, "C", 20)
        r = client.get("/glosas/stats/concentracion-pareto")
        d = r.json()
        top = d["top_eps_concentracion"]
        assert top[0]["eps"] == "A"
        assert top[0]["pct_individual"] == 50.0
        assert top[0]["pct_acumulado"] == 50.0
        assert top[1]["eps"] == "B"
        assert top[1]["pct_acumulado"] == 80.0
        assert top[2]["eps"] == "C"
        assert top[2]["pct_acumulado"] == 100.0
