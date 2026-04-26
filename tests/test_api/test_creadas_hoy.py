"""Tests del endpoint GET /glosas/stats/creadas-hoy (R175 P1)."""
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


def _seed(db, eps="X", factura="F-1", valor=1000, dias_atras=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestCreadasHoy:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/creadas-hoy")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("fecha", "count", "valor_objetado_total",
                    "epss_distintas", "facturas_distintas"):
            assert key in d

    def test_solo_cuenta_hoy(self, client, db_session):
        _seed(db_session, dias_atras=0)
        _seed(db_session, dias_atras=2)  # ayer/anteayer
        r = client.get("/glosas/stats/creadas-hoy")
        d = r.json()
        assert d["count"] == 1

    def test_distintas(self, client, db_session):
        _seed(db_session, eps="A", factura="F-1", valor=1000)
        _seed(db_session, eps="A", factura="F-2", valor=2000)
        _seed(db_session, eps="B", factura="F-1", valor=3000)

        r = client.get("/glosas/stats/creadas-hoy")
        d = r.json()
        assert d["count"] == 3
        assert d["valor_objetado_total"] == 6000
        assert d["epss_distintas"] == 2
        assert d["facturas_distintas"] == 2
