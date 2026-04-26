"""Tests del endpoint GET /glosas/stats/gestores-pareto (R259 P1)."""
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


def _seed(db, gestor, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestGestoresPareto:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/gestores-pareto")
        d = r.json()
        assert d["total_decididas"] == 0
        assert d["gestores_top80"] == []

    def test_concentracion(self, client, db_session):
        # Alice: 8 decididas → 80%
        for _ in range(8):
            _seed(db_session, "Alice")
        # Bob: 1 decidida
        _seed(db_session, "Bob")
        # Carla: 1 decidida
        _seed(db_session, "Carla")

        r = client.get("/glosas/stats/gestores-pareto")
        d = r.json()
        assert d["total_decididas"] == 10
        assert d["total_gestores"] == 3
        # Solo Alice debería estar en top80 (acumula 80% sola)
        assert d["count_gestores_top80"] == 1
        assert d["gestores_top80"][0]["gestor"] == "Alice"

    def test_excluye_no_decididas(self, client, db_session):
        _seed(db_session, "Alice", estado="RADICADA")
        r = client.get("/glosas/stats/gestores-pareto")
        d = r.json()
        assert d["total_decididas"] == 0
