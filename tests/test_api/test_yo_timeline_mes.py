"""Tests del endpoint GET /usuarios/yo/timeline-mes (R389 P1)."""
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


class TestYoTimelineMes:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/timeline-mes")
        d = r.json()
        for k in (
            "mes", "dias_mes", "dia_actual",
            "total_decididas_mes", "serie",
        ):
            assert k in d
        # serie tiene una entrada por día del mes
        assert len(d["serie"]) == d["dias_mes"]

    def test_count(self, client, db_session):
        _seed(db_session)
        _seed(db_session)
        r = client.get("/usuarios/yo/timeline-mes")
        d = r.json()
        assert d["total_decididas_mes"] == 2
        assert d["mejor_dia"]["count"] == 2
