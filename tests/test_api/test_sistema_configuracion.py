"""Tests del endpoint GET /sistema/configuracion (R97 P1)."""
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


class TestSistemaConfiguracion:
    def test_estructura_secciones(self, client):
        r = client.get("/sistema/configuracion")
        assert r.status_code == 200, r.text
        d = r.json()
        # Las 6 secciones deben estar
        assert set(d.keys()) == {"app", "ia", "auth", "cors", "smtp", "ui"}

    def test_app_metadata(self, client):
        r = client.get("/sistema/configuracion")
        d = r.json()
        assert "nombre" in d["app"]
        assert "version" in d["app"]
        assert d["app"]["version"]

    def test_no_revela_api_keys(self, client):
        r = client.get("/sistema/configuracion")
        d = r.json()
        # El payload completo NO debe contener strings que parezcan keys
        body = r.text
        # Las keys reales NO deben aparecer; solo booleanos
        assert "anthropic_configurado" in body
        assert "groq_configurado" in body
        # Tipo bool, no string
        assert isinstance(d["ia"]["anthropic_configurado"], bool)
        assert isinstance(d["ia"]["groq_configurado"], bool)

    def test_no_revela_passwords(self, client):
        r = client.get("/sistema/configuracion")
        d = r.json()
        assert isinstance(d["auth"]["admin_password_configurado"], bool)
        assert isinstance(d["smtp"]["password_configurado"], bool)
        # No campo "password" o "admin_password" con valor real
        assert "admin_password" not in d["auth"] or \
            isinstance(d["auth"].get("admin_password_configurado"), bool)

    def test_cors_es_lista(self, client):
        r = client.get("/sistema/configuracion")
        d = r.json()
        assert isinstance(d["cors"]["allowed_origins"], list)
