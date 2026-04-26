"""Tests del endpoint GET /glosas/codigos-respuesta-catalogo (R137 P1)."""
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


class TestCodigosRespuestaCatalogo:
    def test_estructura(self, client):
        r = client.get("/glosas/codigos-respuesta-catalogo")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("regulacion", "total_codigos", "items"):
            assert key in d
        assert d["total_codigos"] >= 5

    def test_codigos_clave(self, client):
        r = client.get("/glosas/codigos-respuesta-catalogo")
        d = r.json()
        codigos = {it["codigo"] for it in d["items"]}
        # Códigos más usados
        assert "RE9901" in codigos
        assert "RE9602" in codigos
        assert "RE9502" in codigos

    def test_clasificacion_funcional(self, client):
        r = client.get("/glosas/codigos-respuesta-catalogo")
        d = r.json()
        por_codigo = {it["codigo"]: it for it in d["items"]}

        # RE9901, RE9602, RE9502 son DEFENSA
        assert por_codigo["RE9901"]["tipo_funcional"] == "DEFENSA"
        assert por_codigo["RE9602"]["tipo_funcional"] == "DEFENSA"
        # RE9701, RE9801 son ACEPTACION
        assert por_codigo["RE9801"]["tipo_funcional"] == "ACEPTACION"
        # RE2201, RE2202 son EXTEMPORANEA
        assert por_codigo["RE2201"]["tipo_funcional"] == "EXTEMPORANEA"

    def test_orden_alfabetico(self, client):
        r = client.get("/glosas/codigos-respuesta-catalogo")
        d = r.json()
        codigos = [it["codigo"] for it in d["items"]]
        assert codigos == sorted(codigos)
