"""Tests del endpoint GET /glosas/stats/cerradas-hoy (R176 P1)."""
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


def _seed(db, estado="LEVANTADA", valor_rec=1000, dias_dec=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_dec),
    ))
    db.commit()


class TestCerradasHoy:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/cerradas-hoy")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("fecha", "count", "levantadas", "aceptadas",
                    "valor_recuperado_total",
                    "tasa_levantamiento_pct"):
            assert key in d

    def test_solo_cuenta_hoy(self, client, db_session):
        _seed(db_session, dias_dec=0)
        _seed(db_session, dias_dec=2)  # ayer/anteayer
        r = client.get("/glosas/stats/cerradas-hoy")
        d = r.json()
        assert d["count"] == 1

    def test_excluye_abiertas(self, client, db_session):
        _seed(db_session, estado="RADICADA", dias_dec=0)
        r = client.get("/glosas/stats/cerradas-hoy")
        d = r.json()
        assert d["count"] == 0

    def test_tasa_levantamiento(self, client, db_session):
        _seed(db_session, estado="LEVANTADA", valor_rec=5000)
        _seed(db_session, estado="LEVANTADA", valor_rec=3000)
        _seed(db_session, estado="ACEPTADA", valor_rec=0)

        r = client.get("/glosas/stats/cerradas-hoy")
        d = r.json()
        assert d["count"] == 3
        assert d["levantadas"] == 2
        assert d["aceptadas"] == 1
        assert d["valor_recuperado_total"] == 8000
        # 2/3 = 66.67%
        assert d["tasa_levantamiento_pct"] == 66.67
