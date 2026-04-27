"""Tests del endpoint GET /usuarios/yo/proximas-sugerencias (R399 P1)."""
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


def _seed(db, gestor="Alice", dias=10, valor=1000,
          estado="RADICADA", dictamen=None):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
        dictamen=dictamen,
    ))
    db.commit()


class TestProximasSugerencias:
    def test_urgente_primero(self, client, db_session):
        _seed(db_session, dias=-3, valor=5_000_000)
        _seed(db_session, dias=10, valor=100)
        r = client.get("/usuarios/yo/proximas-sugerencias")
        d = r.json()
        # La urgente debe estar primero
        assert d["items"][0]["categoria"] == "URGENTE"

    def test_sin_dictamen_alto(self, client, db_session):
        _seed(
            db_session, dias=10, valor=10_000_000,
            dictamen=None,
        )
        r = client.get("/usuarios/yo/proximas-sugerencias")
        d = r.json()
        cats = [it["categoria"] for it in d["items"]]
        assert "SIN_DICTAMEN" in cats

    def test_sin_glosas(self, client):
        r = client.get("/usuarios/yo/proximas-sugerencias")
        d = r.json()
        assert d["total"] == 0
