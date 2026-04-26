"""Tests del endpoint GET /usuarios/yo/streak (R270 P1)."""
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, dias_atras, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestYoStreak:
    def test_sin_actividad(self, client):
        r = client.get("/usuarios/yo/streak")
        d = r.json()
        assert d["streak_actual"] == 0
        assert d["mejor_streak"] == 0

    def test_streak_consecutivo(self, client, db_session):
        _seed(db_session, "Alice", dias_atras=0)
        _seed(db_session, "Alice", dias_atras=1)
        _seed(db_session, "Alice", dias_atras=2)

        r = client.get("/usuarios/yo/streak")
        d = r.json()
        assert d["streak_actual"] == 3
        assert d["mejor_streak"] == 3
        assert d["dias_con_actividad_total"] == 3

    def test_solo_propias(self, client, db_session):
        _seed(db_session, "Bob", dias_atras=0)
        r = client.get("/usuarios/yo/streak")
        d = r.json()
        assert d["streak_actual"] == 0
        assert d["dias_con_actividad_total"] == 0
