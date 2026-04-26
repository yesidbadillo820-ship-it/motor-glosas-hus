"""Tests del endpoint GET /glosas/stats/dias-decision-promedio-mes (R295 P1)."""
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


def _seed(db, dias_decision):
    creado = ahora_utc() - timedelta(days=dias_decision)
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=creado,
        fecha_decision_eps=ahora_utc(),
    ))
    db.commit()


class TestDiasDecisionPromedioMes:
    def test_promedio_calcula(self, client, db_session):
        _seed(db_session, dias_decision=10)
        _seed(db_session, dias_decision=20)
        _seed(db_session, dias_decision=30)
        # Promedio: 20

        r = client.get(
            "/glosas/stats/dias-decision-promedio-mes?meses=2"
        )
        d = r.json()
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["count"] == 3
        assert mes["promedio_dias"] == 20.0
        assert mes["mediana_dias"] == 20
        assert mes["max_dias"] == 30

    def test_vacio(self, client):
        r = client.get("/glosas/stats/dias-decision-promedio-mes")
        d = r.json()
        assert d["serie"] == []
