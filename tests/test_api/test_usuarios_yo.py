"""Tests del endpoint /usuarios/yo (R81 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
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
def usuario(db_session):
    u = UsuarioRecord(
        id=1, email="auditor@hus.com", nombre="Juan Pérez",
        rol="AUDITOR", activo=1,
        password_hash=get_password_hash("xxxx"),
        creado_en=ahora_utc(),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestUsuariosYo:
    def test_devuelve_metadata_publica(self, client):
        r = client.get("/usuarios/yo")
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == "auditor@hus.com"
        assert d["nombre"] == "Juan Pérez"
        assert d["rol"] == "AUDITOR"
        assert d["activo"] is True

    def test_no_revela_password_hash(self, client):
        """SECURITY: NUNCA debe exponer password_hash ni totp_secret.
        Los campos must_change_password / totp_activo SÍ son OK
        (son flags públicos de estado, no secretos)."""
        r = client.get("/usuarios/yo")
        body = r.text
        # Lo prohibido específicamente es:
        assert "password_hash" not in body
        assert "totp_secret" not in body
        # No debe aparecer ningún hash bcrypt típico
        assert "$2b$" not in body
        assert "$2a$" not in body

    def test_estructura_completa(self, client):
        r = client.get("/usuarios/yo")
        d = r.json()
        for k in ("id", "email", "nombre", "rol", "activo",
                  "totp_activo", "must_change_password", "creado_en"):
            assert k in d
