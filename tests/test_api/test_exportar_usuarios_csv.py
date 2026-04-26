"""Tests del endpoint GET /admin/usuarios/exportar.csv (R105 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", nombre="Root",
        rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx_secreto"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestExportarUsuariosCSV:
    def test_csv_content_type(self, client):
        r = client.get("/admin/usuarios/exportar.csv")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]
        assert ".csv" in r.headers["content-disposition"]

    def test_header_row(self, client):
        r = client.get("/admin/usuarios/exportar.csv")
        primera = r.text.split("\n")[0]
        # Las 10 columnas esperadas
        for col in ("id", "email", "nombre", "rol", "activo",
                    "totp_activo", "must_change_password",
                    "creado_en", "ultimo_login", "fallos_login"):
            assert col in primera

    def test_incluye_usuarios(self, client, db_session, usuario_super):
        # Agregar otro usuario
        db_session.add(UsuarioRecord(
            id=2, email="alice@x", nombre="Alice", rol="AUDITOR",
            activo=1, password_hash=get_password_hash("y"),
        ))
        db_session.commit()

        r = client.get("/admin/usuarios/exportar.csv")
        body = r.text
        assert "root@hus.gov.co" in body
        assert "alice@x" in body

    def test_no_revela_password_hash(self, client):
        r = client.get("/admin/usuarios/exportar.csv")
        body = r.text
        # El bcrypt prefix NO debe aparecer en ninguna línea
        assert "$2b$" not in body
        assert "$2a$" not in body
        # La password en clear tampoco
        assert "xxxx_secreto" not in body

    def test_no_revela_totp_secret(self, client, db_session):
        # Si hubiera totp_secret, no debe filtrarse
        db_session.add(UsuarioRecord(
            id=2, email="2fa@x", nombre="2FA", rol="AUDITOR",
            activo=1, password_hash="x",
            totp_secret="JBSWY3DPEHPK3PXP",  # secret de prueba
            totp_activo=1,
        ))
        db_session.commit()

        r = client.get("/admin/usuarios/exportar.csv")
        body = r.text
        assert "JBSWY3DPEHPK3PXP" not in body
