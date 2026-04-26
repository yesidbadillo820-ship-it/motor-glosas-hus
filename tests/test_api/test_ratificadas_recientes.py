"""Tests del endpoint GET /glosas/stats/ratificadas-recientes (R347 P1)."""
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


def _seed(db, dias_atras, estado="RATIFICADA", aceptado=500):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_aceptado=aceptado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestRatificadasRecientes:
    def test_filtra(self, client, db_session):
        _seed(db_session, dias_atras=5)
        _seed(db_session, dias_atras=15)
        # Ratificada fuera de ventana 30
        _seed(db_session, dias_atras=100)
        # No ratificada
        _seed(db_session, dias_atras=2, estado="LEVANTADA")

        r = client.get(
            "/glosas/stats/ratificadas-recientes?dias=30"
        )
        d = r.json()
        assert d["total"] == 2
        assert d["valor_aceptado_total"] == 1000

    def test_orden_desc(self, client, db_session):
        _seed(db_session, dias_atras=10)
        _seed(db_session, dias_atras=2)
        r = client.get(
            "/glosas/stats/ratificadas-recientes?dias=30"
        )
        d = r.json()
        # Más reciente primero
        ids_esperados = (
            d["items"][0]["fecha_decision_eps"]
            > d["items"][1]["fecha_decision_eps"]
        )
        assert ids_esperados
