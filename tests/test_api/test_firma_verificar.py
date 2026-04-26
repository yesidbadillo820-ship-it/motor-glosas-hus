"""Tests del endpoint /firma/verificar (R85 P1)."""
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


class TestFirmaVerificar:
    def test_firma_real_valida(self, client):
        """Generar una firma real con firmar_dictamen() y verificarla."""
        from app.services.firma_digital import firmar_dictamen
        info = firmar_dictamen(
            texto_dictamen="contenido del dictamen prueba",
            firmante_email="auditor@hus.com",
            glosa_id=42,
        )
        r = client.post("/firma/verificar", json={
            "hash": info["hash"],
            "firma": info["firma"],
            "firmante": info["firmante"],
            "glosa_id": 42,
            "timestamp": info["timestamp"],
            "alg": info["alg"],
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["valida"] is True

    def test_firma_alterada_invalida(self, client):
        """Modificar la firma → debe fallar validación."""
        from app.services.firma_digital import firmar_dictamen
        info = firmar_dictamen(
            texto_dictamen="texto original",
            firmante_email="x@hus.com",
            glosa_id=1,
        )
        # Alterar último char de la firma
        firma_alterada = info["firma"][:-2] + "XX"
        r = client.post("/firma/verificar", json={
            "hash": info["hash"],
            "firma": firma_alterada,
            "firmante": info["firmante"],
            "glosa_id": 1,
            "timestamp": info["timestamp"],
            "alg": info["alg"],
        })
        d = r.json()
        assert d["valida"] is False

    def test_hash_alterado_invalida(self, client):
        """Si cambian el hash (ej. modificaron el documento) → false."""
        from app.services.firma_digital import firmar_dictamen
        info = firmar_dictamen(
            texto_dictamen="texto X",
            firmante_email="x@hus.com",
            glosa_id=2,
        )
        r = client.post("/firma/verificar", json={
            "hash": "0" * 64,  # hash distinto
            "firma": info["firma"],
            "firmante": info["firmante"],
            "glosa_id": 2,
            "timestamp": info["timestamp"],
            "alg": info["alg"],
        })
        assert r.json()["valida"] is False

    def test_payload_invalido_422(self, client):
        """Pydantic rechaza payload mal formado."""
        r = client.post("/firma/verificar", json={"hash": "x"})
        assert r.status_code == 422

    def test_response_incluye_verificado_por(self, client):
        from app.services.firma_digital import firmar_dictamen
        info = firmar_dictamen(
            texto_dictamen="x", firmante_email="x@hus.com", glosa_id=1,
        )
        r = client.post("/firma/verificar", json={
            "hash": info["hash"],
            "firma": info["firma"],
            "firmante": info["firmante"],
            "glosa_id": 1,
            "timestamp": info["timestamp"],
            "alg": info["alg"],
        })
        assert r.json()["verificado_por"] == "auditor@hus.com"
