"""Tests del endpoint GET /sistema/inventario-funcionalidades (R200 P1)."""
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


class TestInventarioFuncionalidades:
    def test_estructura(self, client):
        r = client.get("/sistema/inventario-funcionalidades")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("dominios", "regulacion", "stack_principal"):
            assert key in d

    def test_dominios_clave(self, client):
        r = client.get("/sistema/inventario-funcionalidades")
        d = r.json()
        nombres = [dom["nombre"] for dom in d["dominios"]]
        for n in ("Glosas", "Estadísticas", "Auditoría",
                  "Operación", "IA y prompts", "Sistema"):
            assert n in nombres

    def test_dominios_tienen_metadata(self, client):
        r = client.get("/sistema/inventario-funcionalidades")
        d = r.json()
        for dom in d["dominios"]:
            assert "nombre" in dom
            assert "descripcion" in dom
            assert "endpoints_aprox" in dom
            assert "funcionalidades_clave" in dom
            assert isinstance(dom["funcionalidades_clave"], list)
            assert len(dom["funcionalidades_clave"]) > 0

    def test_regulacion_y_stack(self, client):
        r = client.get("/sistema/inventario-funcionalidades")
        d = r.json()
        assert "principal" in d["regulacion"]
        assert "Resolución 2284" in d["regulacion"]["principal"]
        assert "framework" in d["stack_principal"]
