"""Tests del endpoint /consulta-normativa/normas/export.json (R79 P2)."""
from __future__ import annotations

import json

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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestExportNormas:
    def test_estructura_basica(self, client):
        r = client.get("/consulta-normativa/normas/export.json")
        assert r.status_code == 200
        d = json.loads(r.text)
        assert "metadata" in d
        assert "normas" in d

    def test_metadata_completa(self, client):
        r = client.get("/consulta-normativa/normas/export.json")
        d = json.loads(r.text)
        m = d["metadata"]
        assert "exportado_en" in m
        assert "exportado_por" in m
        assert "total_normas" in m
        assert m["total_normas"] >= 100  # R52 B (101 normas)

    def test_normas_tienen_estructura(self, client):
        r = client.get("/consulta-normativa/normas/export.json")
        d = json.loads(r.text)
        # Debe haber al menos 100 normas según R52 B
        assert len(d["normas"]) >= 100
        # Cada norma trae estructura mínima
        for n in d["normas"][:5]:
            for k in ("clave", "nombre", "titulo", "vigente", "keywords"):
                assert k in n

    def test_descarga_attachment(self, client):
        r = client.get("/consulta-normativa/normas/export.json")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".json" in r.headers.get("content-disposition", "")

    def test_incluye_normas_clave(self, client):
        r = client.get("/consulta-normativa/normas/export.json")
        d = json.loads(r.text)
        claves = [n["clave"] for n in d["normas"]]
        # Algunas normas críticas deben estar
        assert "LEY 1438 DE 2011" in claves
        assert "RESOLUCION 2284 DE 2023" in claves
