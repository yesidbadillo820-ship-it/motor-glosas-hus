"""Tests del endpoint GET /glosas/stats/glosas-sin-fecha-decision (R322 P1)."""
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


def _seed(db, estado, fecha=None):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=fecha,
    ))
    db.commit()


class TestGlosasSinFechaDecision:
    def test_filtra(self, client, db_session):
        _seed(db_session, "LEVANTADA", fecha=None)
        _seed(db_session, "RATIFICADA", fecha=None)
        _seed(db_session, "LEVANTADA", fecha=ahora_utc())  # OK
        _seed(db_session, "RADICADA", fecha=None)  # no decidida

        r = client.get("/glosas/stats/glosas-sin-fecha-decision")
        d = r.json()
        assert d["total_sin_fecha_decision"] == 2

    def test_vacio(self, client):
        r = client.get("/glosas/stats/glosas-sin-fecha-decision")
        d = r.json()
        assert d["total_sin_fecha_decision"] == 0
