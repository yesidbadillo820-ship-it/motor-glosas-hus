"""Tests del endpoint GET /sistema/db-schema (R105 P2)."""
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


class TestDbSchema:
    def test_estructura(self, client):
        r = client.get("/sistema/db-schema")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_tablas", "incluir_columnas", "items"):
            assert key in d
        assert d["total_tablas"] > 0

    def test_lista_tablas_principales(self, client):
        r = client.get("/sistema/db-schema")
        d = r.json()
        nombres = {it["tabla"] for it in d["items"]}
        assert "historial" in nombres  # GlosaRecord
        assert "usuarios" in nombres
        assert "audit_log" in nombres

    def test_columnas_con_metadata(self, client):
        r = client.get("/sistema/db-schema")
        d = r.json()
        usuarios = next(it for it in d["items"] if it["tabla"] == "usuarios")
        # Debe tener columnas con metadata
        cols = {c["nombre"]: c for c in usuarios["columnas"]}
        assert "id" in cols
        assert cols["id"]["primary_key"] is True
        assert "email" in cols

    def test_sin_columnas_si_no_se_pide(self, client):
        r = client.get("/sistema/db-schema?incluir_columnas=false")
        d = r.json()
        assert d["incluir_columnas"] is False
        for it in d["items"]:
            # Cuando no se piden columnas, se devuelve null
            assert it["columnas"] is None
            assert it["total_columnas"] > 0

    def test_orden_alfabetico(self, client):
        r = client.get("/sistema/db-schema")
        d = r.json()
        nombres = [it["tabla"] for it in d["items"]]
        assert nombres == sorted(nombres)
