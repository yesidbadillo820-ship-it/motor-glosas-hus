"""Tests del CRUD /contratos (R75 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ContratoRecord, UsuarioRecord


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


class TestContratosCrud:
    def test_listar_vacio(self, client):
        r = client.get("/contratos/")
        assert r.status_code == 200
        assert r.json() == []

    def test_upsert_crea_nuevo(self, client, db_session):
        r = client.post("/contratos/upsert", json={
            "eps": "FAMISANAR",
            "detalles": "Contrato S-13-1-03-1-04958 vigente hasta 2027",
        })
        assert r.status_code == 200, r.text
        # Verificar en BD
        c = db_session.query(ContratoRecord).filter_by(eps="FAMISANAR").first()
        assert c is not None
        assert "S-13-1-03-1-04958" in c.detalles

    def test_upsert_actualiza_existente(self, client, db_session):
        client.post("/contratos/upsert", json={
            "eps": "FAMISANAR",
            "detalles": "Versión vieja del contrato",
        })
        # Update mismo EPS
        r = client.post("/contratos/upsert", json={
            "eps": "FAMISANAR",
            "detalles": "Versión nueva del contrato actualizada",
        })
        assert r.status_code == 200
        # Solo 1 fila para esa EPS
        n = db_session.query(ContratoRecord).filter_by(eps="FAMISANAR").count()
        assert n == 1
        c = db_session.query(ContratoRecord).filter_by(eps="FAMISANAR").first()
        assert "actualizada" in c.detalles

    def test_listar_devuelve_creado(self, client):
        client.post("/contratos/upsert", json={
            "eps": "SALUD TOTAL",
            "detalles": "Contrato vigente con tarifas pactadas SOAT 100%",
        })
        r = client.get("/contratos/")
        items = r.json()
        assert len(items) >= 1
        assert any(it["eps"] == "SALUD TOTAL" for it in items)

    def test_eliminar_existente(self, client, db_session):
        client.post("/contratos/upsert", json={
            "eps": "ALIANSALUD",
            "detalles": "contrato de prueba",
        })
        r = client.delete("/contratos/ALIANSALUD")
        assert r.status_code == 200
        c = db_session.query(ContratoRecord).filter_by(eps="ALIANSALUD").first()
        assert c is None

    def test_eliminar_inexistente_404(self, client):
        r = client.delete("/contratos/INEXISTENTE_XYZ")
        assert r.status_code == 404
