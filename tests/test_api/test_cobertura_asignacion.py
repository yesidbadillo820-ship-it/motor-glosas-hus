"""Tests del endpoint GET /glosas/stats/cobertura-asignacion (R313 P1)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestCoberturaAsignacion:
    def test_metricas(self, client, db_session):
        _seed(db_session, gestor_nombre="Alice")
        _seed(db_session, gestor_nombre=None)

        r = client.get("/glosas/stats/cobertura-asignacion")
        d = r.json()
        assert d["total_glosas"] == 2
        gestor = next(
            x for x in d["items"] if x["campo"] == "gestor_nombre"
        )
        assert gestor["count"] == 1
        assert gestor["pct_cobertura"] == 50.0
        assert gestor["faltantes"] == 1

    def test_vacio(self, client):
        r = client.get("/glosas/stats/cobertura-asignacion")
        d = r.json()
        assert d["total_glosas"] == 0
        assert d["items"] == []
