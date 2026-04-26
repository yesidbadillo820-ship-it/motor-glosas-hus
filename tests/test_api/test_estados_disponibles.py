"""Tests del endpoint GET /glosas/estados-disponibles (R136 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


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


class TestEstadosDisponibles:
    def test_estructura(self, client):
        r = client.get("/glosas/estados-disponibles")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "total" in d
        assert "estados" in d
        assert d["total"] == len(d["estados"])
        assert d["total"] >= 6  # mínimo razonable

    def test_estados_clave(self, client):
        r = client.get("/glosas/estados-disponibles")
        d = r.json()
        claves = {e["clave"] for e in d["estados"]}
        for clave in ("RADICADA", "RESPONDIDA", "RATIFICADA",
                      "LEVANTADA", "ACEPTADA", "CONCILIADA"):
            assert clave in claves

    def test_cada_estado_tiene_metadata(self, client):
        r = client.get("/glosas/estados-disponibles")
        d = r.json()
        for e in d["estados"]:
            assert "clave" in e
            assert "nombre" in e
            assert "descripcion" in e
            assert "es_cerrado" in e
            assert "color" in e
            assert isinstance(e["es_cerrado"], bool)

    def test_estados_cerrados_marcados(self, client):
        r = client.get("/glosas/estados-disponibles")
        d = r.json()
        por_clave = {e["clave"]: e for e in d["estados"]}
        # Estados cerrados conocidos
        for k in ("LEVANTADA", "ACEPTADA", "CONCILIADA", "ARCHIVADA"):
            assert por_clave[k]["es_cerrado"] is True
        # Estados abiertos
        for k in ("RADICADA", "RESPONDIDA"):
            assert por_clave[k]["es_cerrado"] is False
