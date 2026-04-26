"""Tests del endpoint GET /glosas/stats/dgh-radicacion-tiempo (R264 P1)."""
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


def _seed(db, dias):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dias_radicacion_dgh=dias,
    ))
    db.commit()


class TestDGHRadicacionTiempo:
    def test_buckets(self, client, db_session):
        for d in [3, 5, 15, 45, 75, 120]:
            _seed(db_session, d)

        r = client.get("/glosas/stats/dgh-radicacion-tiempo")
        d = r.json()
        bm = {b["rango"]: b["count"] for b in d["buckets"]}
        assert bm["0-7"] == 2
        assert bm["8-30"] == 1
        assert bm["31-60"] == 1
        assert bm["61-90"] == 1
        assert bm["91+"] == 1
        assert d["total_glosas"] == 6
        assert d["max_dias"] == 120

    def test_vacio(self, client):
        r = client.get("/glosas/stats/dgh-radicacion-tiempo")
        d = r.json()
        assert d["total_glosas"] == 0
        assert d["promedio_dias"] == 0.0
