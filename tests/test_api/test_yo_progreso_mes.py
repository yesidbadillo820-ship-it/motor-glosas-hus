"""Tests del endpoint GET /usuarios/yo/progreso-mes (R387 P1)."""
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
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
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


def _seed(db, gestor="Alice", estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        fecha_decision_eps=ahora_utc(),
    ))
    db.commit()


class TestProgresoMes:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/progreso-mes")
        d = r.json()
        for k in (
            "decididas_mes_actual", "meta_mensual",
            "progreso_pct", "ritmo_diario_actual",
            "ritmo_diario_necesario", "nivel", "mensaje",
        ):
            assert k in d

    def test_contar_mes(self, client, db_session):
        _seed(db_session)
        _seed(db_session)
        r = client.get("/usuarios/yo/progreso-mes")
        d = r.json()
        assert d["decididas_mes_actual"] == 2
        assert d["meta_mensual"] >= 5

    def test_meta_default_minima(self, client):
        r = client.get("/usuarios/yo/progreso-mes")
        d = r.json()
        # Sin histórico la meta es 5
        assert d["meta_mensual"] == 5
