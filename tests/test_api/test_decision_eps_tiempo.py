"""Tests del endpoint GET /glosas/stats/decision-eps-tiempo-distribucion (R285 P1)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed(db, dias_decision):
    creado = ahora_utc() - timedelta(days=dias_decision)
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=creado,
        fecha_decision_eps=ahora_utc(),
    ))
    db.commit()


class TestDecisionEPSTiempo:
    def test_buckets(self, client, db_session):
        _seed(db_session, dias_decision=5)    # 0-15
        _seed(db_session, dias_decision=20)   # 16-30
        _seed(db_session, dias_decision=45)   # 31-60
        _seed(db_session, dias_decision=120)  # >90

        r = client.get(
            "/glosas/stats/decision-eps-tiempo-distribucion"
        )
        d = r.json()
        bm = {b["rango_dias"]: b["count"] for b in d["buckets"]}
        assert bm["0-15"] == 1
        assert bm["16-30"] == 1
        assert bm["31-60"] == 1
        assert bm[">90"] == 1
        assert d["total_glosas"] == 4

    def test_vacio(self, client):
        r = client.get(
            "/glosas/stats/decision-eps-tiempo-distribucion"
        )
        d = r.json()
        assert d["total_glosas"] == 0
        assert d["promedio_dias"] == 0.0
