"""Tests del endpoint GET /glosas/stats/recientes-decididas (R319 P1)."""
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


def _seed(db, glosa_id, dias_atras, estado="LEVANTADA"):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestRecientesDecididas:
    def test_orden(self, client, db_session):
        _seed(db_session, 1, dias_atras=10)
        _seed(db_session, 2, dias_atras=2)
        _seed(db_session, 3, dias_atras=5)

        r = client.get("/glosas/stats/recientes-decididas")
        d = r.json()
        # Más reciente primero
        ids = [it["glosa_id"] for it in d["items"]]
        assert ids == [2, 3, 1]

    def test_excluye_no_decididas(self, client, db_session):
        _seed(db_session, 1, dias_atras=1, estado="RADICADA")
        r = client.get("/glosas/stats/recientes-decididas")
        d = r.json()
        assert d["items"] == []

    def test_limit(self, client, db_session):
        for i in range(5):
            _seed(db_session, i + 1, dias_atras=i)
        r = client.get("/glosas/stats/recientes-decididas?limit=2")
        d = r.json()
        assert len(d["items"]) == 2
