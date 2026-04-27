"""Tests del endpoint GET /glosas/stats/comparativa-anio (R383 P1)."""
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
    return UsuarioRecord(id=1, email="x@x", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, dias_atras, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestComparativaAnio:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/comparativa-anio")
        d = r.json()
        assert "year_actual" in d
        assert "year_anterior" in d
        assert len(d["serie"]) == 12

    def test_count_anio_actual(self, client, db_session):
        _seed(db_session, dias_atras=10)
        r = client.get("/glosas/stats/comparativa-anio")
        d = r.json()
        assert d["total_actual_count"] >= 1
