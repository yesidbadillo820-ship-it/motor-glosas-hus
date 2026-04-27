"""Tests del endpoint GET /usuarios/yo/insights (R385 P1)."""
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


def _seed(db, gestor="Alice", dias=10, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
    ))
    db.commit()


class TestInsights:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/insights")
        d = r.json()
        assert "items" in d
        assert "total_insights" in d

    def test_vencidas_genera_insight(self, client, db_session):
        _seed(db_session, dias=-5)
        r = client.get("/usuarios/yo/insights")
        d = r.json()
        assert any(it["tipo"] == "ATENCION" for it in d["items"])

    def test_backlog_alto(self, client, db_session):
        for _ in range(35):
            _seed(db_session, dias=10)
        r = client.get("/usuarios/yo/insights")
        d = r.json()
        assert any("Backlog" in it["titulo"] for it in d["items"])
