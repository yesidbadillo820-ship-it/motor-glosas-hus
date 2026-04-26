"""Tests del endpoint GET /sistema/api-endpoints (R113 P2)."""
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


class TestApiEndpoints:
    def test_estructura(self, client):
        r = client.get("/sistema/api-endpoints")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_endpoints", "por_tag", "items"):
            assert key in d
        assert d["total_endpoints"] > 50  # tenemos muchos endpoints

    def test_lista_endpoints_conocidos(self, client):
        r = client.get("/sistema/api-endpoints")
        d = r.json()
        paths = {it["path"] for it in d["items"]}
        # Algunos endpoints conocidos deben estar
        assert "/sistema/api-endpoints" in paths
        assert "/sistema/version" in paths
        assert "/glosas/{glosa_id}" in paths

    def test_por_tag_agrupacion(self, client):
        r = client.get("/sistema/api-endpoints")
        d = r.json()
        # Tag "glosas" debe tener muchos endpoints
        assert d["por_tag"].get("glosas", 0) > 20
        assert "sistema" in d["por_tag"]

    def test_metodos_incluidos_por_default(self, client):
        r = client.get("/sistema/api-endpoints")
        d = r.json()
        assert "methods" in d["items"][0]

    def test_sin_metodos_si_se_excluye(self, client):
        r = client.get("/sistema/api-endpoints?incluir_metodos=false")
        d = r.json()
        assert "methods" not in d["items"][0]

    def test_paths_ordenados(self, client):
        r = client.get("/sistema/api-endpoints")
        d = r.json()
        paths = [it["path"] for it in d["items"]]
        assert paths == sorted(paths)
