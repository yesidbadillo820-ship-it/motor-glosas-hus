"""Tests del endpoint GET /glosas/stats/tecnico-recepcion-actividad (R263 P1)."""
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


def _seed(db, tecnico, eps="X", devolucion=None):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        tecnico_recepcion=tecnico,
        es_devolucion=devolucion,
    ))
    db.commit()


class TestTecnicoRecepcion:
    def test_filtra_sin_tecnico(self, client, db_session):
        _seed(db_session, "Carlos")
        _seed(db_session, None)
        _seed(db_session, "")
        r = client.get("/glosas/stats/tecnico-recepcion-actividad")
        d = r.json()
        assert d["total_tecnicos"] == 1
        assert d["items"][0]["tecnico_recepcion"] == "Carlos"

    def test_eps_distintas(self, client, db_session):
        _seed(db_session, "Carlos", eps="SANITAS")
        _seed(db_session, "Carlos", eps="EPS001")
        _seed(db_session, "Carlos", eps="SANITAS")  # duplicada
        r = client.get("/glosas/stats/tecnico-recepcion-actividad")
        d = r.json()
        assert d["items"][0]["eps_distintas"] == 2
        assert d["items"][0]["total_glosas"] == 3

    def test_devoluciones(self, client, db_session):
        _seed(db_session, "Ana", devolucion="1")
        _seed(db_session, "Ana", devolucion=None)
        r = client.get("/glosas/stats/tecnico-recepcion-actividad")
        d = r.json()
        assert d["items"][0]["count_devoluciones"] == 1

    def test_limit(self, client, db_session):
        for i in range(5):
            _seed(db_session, f"T{i}")
        r = client.get(
            "/glosas/stats/tecnico-recepcion-actividad?limit=2"
        )
        d = r.json()
        assert len(d["items"]) == 2
        assert d["total_tecnicos"] == 5
