"""Tests del endpoint GET /glosas/stats/cobranza-pareto-eps (R254 P1)."""
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


class TestCobranzaParetoEPS:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cobranza-pareto-eps")
        d = r.json()
        assert d["valor_total"] == 0
        assert d["eps_top80"] == []

    def test_pareto_80_20(self, client, db_session):
        # 1 EPS con 80% (concentración alta)
        _seed(db_session, "GIGANTE", 80_000_000)
        for i in range(5):
            _seed(db_session, f"PEQUE_{i}", 4_000_000)
        # Total = 80M + 20M = 100M
        # GIGANTE = 80% → solo necesita 1 EPS para acumular 80%

        r = client.get("/glosas/stats/cobranza-pareto-eps")
        d = r.json()
        assert d["valor_total"] == 100_000_000
        assert d["count_eps_top80"] == 1
        assert d["eps_top80"][0]["eps"] == "GIGANTE"
