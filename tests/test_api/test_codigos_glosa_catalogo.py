"""Tests del endpoint GET /glosas/codigos-glosa-catalogo (R136 P2)."""
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


class TestCodigosGlosaCatalogo:
    def test_estructura(self, client):
        r = client.get("/glosas/codigos-glosa-catalogo")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("regulacion", "total_codigos", "por_grupo", "items"):
            assert key in d
        assert d["total_codigos"] > 30  # mínimo razonable

    def test_codigos_clave(self, client):
        r = client.get("/glosas/codigos-glosa-catalogo")
        d = r.json()
        codigos = {it["codigo"] for it in d["items"]}
        assert "TA0201" in codigos
        assert "FA0603" in codigos

    def test_filtro_por_grupo(self, client):
        r = client.get("/glosas/codigos-glosa-catalogo?grupo=FA")
        d = r.json()
        for it in d["items"]:
            assert it["grupo"] == "FA"
        assert d["filtro_grupo"] == "FA"

    def test_grupo_invalido_400(self, client):
        r = client.get("/glosas/codigos-glosa-catalogo?grupo=XYZ")
        assert r.status_code == 400

    def test_orden_alfabetico(self, client):
        r = client.get("/glosas/codigos-glosa-catalogo?grupo=TA")
        d = r.json()
        codigos = [it["codigo"] for it in d["items"]]
        assert codigos == sorted(codigos)
