"""Tests del endpoint GET /glosas/stats/decisiones-por-dia (R297 P1)."""
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


def _seed(db, dias_atras, estado):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestDecisionesPorDia:
    def test_serie(self, client, db_session):
        _seed(db_session, 0, "LEVANTADA")
        _seed(db_session, 0, "RATIFICADA")
        _seed(db_session, 1, "LEVANTADA")
        # Más allá de la ventana
        _seed(db_session, 100, "LEVANTADA")

        r = client.get("/glosas/stats/decisiones-por-dia?dias=7")
        d = r.json()
        # Solo dos días con actividad en la ventana
        assert d["total_dias_con_actividad"] == 2
        total = sum(s["total"] for s in d["serie"])
        assert total == 3

    def test_vacio(self, client):
        r = client.get("/glosas/stats/decisiones-por-dia")
        d = r.json()
        assert d["serie"] == []
