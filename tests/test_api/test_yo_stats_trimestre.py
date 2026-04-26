"""Tests del endpoint GET /usuarios/yo/stats-trimestre (R365 P1)."""
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


def _seed(db, gestor, estado="LEVANTADA", recuperado=100):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=ahora_utc(),
    ))
    db.commit()


class TestYoStatsTrimestre:
    def test_metricas(self, client, db_session):
        _seed(db_session, "Alice", "LEVANTADA", recuperado=500)
        _seed(db_session, "Alice", "RATIFICADA", recuperado=0)
        # Otro gestor
        _seed(db_session, "Bob", "LEVANTADA", recuperado=999)

        r = client.get("/usuarios/yo/stats-trimestre")
        d = r.json()
        assert d["decididas"] == 2
        assert d["levantadas"] == 1
        assert d["tasa_levantamiento_pct"] == 50.0
        assert d["valor_recuperado_total"] == 500
