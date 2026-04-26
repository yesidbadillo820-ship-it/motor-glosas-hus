"""Tests del endpoint GET /sistema/jobs-programados (R104 P1)."""
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


class TestJobsProgramados:
    def test_estructura(self, client):
        r = client.get("/sistema/jobs-programados")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_jobs", "activos", "items"):
            assert key in d

    def test_lista_3_jobs_principales(self, client):
        r = client.get("/sistema/jobs-programados")
        d = r.json()
        nombres = {j["nombre"] for j in d["items"]}
        assert "pre_analisis_ia" in nombres
        assert "mantenimiento_bd" in nombres
        assert "digest_email" in nombres

    def test_cada_job_tiene_metadata(self, client):
        r = client.get("/sistema/jobs-programados")
        d = r.json()
        for j in d["items"]:
            assert "nombre" in j
            assert "descripcion" in j
            assert "frecuencia" in j
            assert "activo" in j
            assert "modulo" in j
