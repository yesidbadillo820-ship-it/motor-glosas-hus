"""Tests del endpoint GET /usuarios/yo/sugerencias-orden (R394 P1)."""
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
          estado="RADICADA", eps="X", codigo="C"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
    ))
    db.commit()


class TestSugerenciasOrden:
    def test_orden_por_score(self, client, db_session):
        # Glosa 1: vencida + alto valor → score alto
        _seed(db_session, dias=-3, valor=10_000_000)
        # Glosa 2: tranquila, valor bajo → score bajo
        _seed(db_session, dias=20, valor=100)
        r = client.get("/usuarios/yo/sugerencias-orden")
        d = r.json()
        assert d["total"] == 2
        # La urgente debe ir primero
        assert d["items"][0]["dias_restantes"] == -3

    def test_motivo_legible(self, client, db_session):
        _seed(db_session, dias=-5, valor=8_000_000)
        r = client.get("/usuarios/yo/sugerencias-orden")
        d = r.json()
        m = d["items"][0]["motivo"]
        assert "vencida" in m
        assert "alto valor" in m

    def test_sin_glosas(self, client):
        r = client.get("/usuarios/yo/sugerencias-orden")
        d = r.json()
        assert d["total"] == 0
