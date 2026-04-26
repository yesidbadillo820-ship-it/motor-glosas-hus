"""Tests del endpoint GET /sistema/dependencias (R91 P2)."""
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


class TestSistemaDependencias:
    def test_lista_dependencias_directas(self, client):
        r = client.get("/sistema/dependencias")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["incluye_indirectas"] is False
        assert d["total"] > 0
        # Deben aparecer fastapi y sqlalchemy (core del stack)
        nombres = {p["nombre"] for p in d["paquetes"]}
        assert "fastapi" in nombres
        assert "sqlalchemy" in nombres
        assert "pydantic" in nombres

    def test_cada_paquete_tiene_version(self, client):
        r = client.get("/sistema/dependencias")
        d = r.json()
        for p in d["paquetes"]:
            assert "nombre" in p
            assert "version" in p
            assert p["version"]
            assert isinstance(p["version"], str)

    def test_paquetes_ordenados(self, client):
        r = client.get("/sistema/dependencias")
        d = r.json()
        nombres = [p["nombre"] for p in d["paquetes"]]
        assert nombres == sorted(nombres)

    def test_incluir_indirectas_devuelve_mas(self, client):
        r1 = client.get("/sistema/dependencias")
        r2 = client.get("/sistema/dependencias?incluir_indirectas=true")
        # incluir_indirectas debe devolver >= que solo directas
        assert r2.json()["total"] >= r1.json()["total"]
        assert r2.json()["incluye_indirectas"] is True
