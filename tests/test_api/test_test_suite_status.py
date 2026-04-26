"""Tests del endpoint GET /sistema/test-suite-status (R142 P1)."""
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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestTestSuiteStatus:
    def test_estructura(self, client):
        r = client.get("/sistema/test-suite-status")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_archivos", "total_lineas",
                    "por_directorio", "items"):
            assert key in d
        # En esta corrida hay muchos tests
        assert d["total_archivos"] > 50

    def test_test_api_presente(self, client):
        r = client.get("/sistema/test-suite-status")
        d = r.json()
        # test_api debe estar en por_directorio
        assert "test_api" in d["por_directorio"]
        assert d["por_directorio"]["test_api"] > 50

    def test_items_tienen_metadata(self, client):
        r = client.get("/sistema/test-suite-status")
        d = r.json()
        for it in d["items"][:5]:
            assert "archivo" in it
            assert "tamano_bytes" in it
            assert "lineas" in it
            assert it["tamano_bytes"] > 0
            assert it["lineas"] > 0
            assert it["archivo"].startswith("test_") or "/test_" in it["archivo"]
