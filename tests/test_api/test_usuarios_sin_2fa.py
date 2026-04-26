"""Tests del endpoint GET /usuarios/sin-2fa (R191 P1)."""
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
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
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


def _seed(db, email, totp=None, activo=1):
    db.add(UsuarioRecord(
        email=email, rol="AUDITOR", activo=activo,
        totp_secret=totp,
        password_hash=get_password_hash("y"),
    ))
    db.commit()


class TestUsuariosSin2FA:
    def test_estructura(self, client):
        r = client.get("/usuarios/sin-2fa")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_sin_2fa", "items"):
            assert key in d

    def test_detecta_sin_2fa(self, client, db_session):
        _seed(db_session, "alice@x", totp=None)
        _seed(db_session, "bob@x", totp="ABC123")
        _seed(db_session, "carol@x", totp="")

        r = client.get("/usuarios/sin-2fa")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        # alice (None) y carol ("") están sin 2FA
        # también el root del seed
        assert "alice@x" in emails
        assert "carol@x" in emails
        assert "bob@x" not in emails

    def test_excluye_inactivos(self, client, db_session):
        _seed(db_session, "off@x", totp=None, activo=0)
        r = client.get("/usuarios/sin-2fa")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "off@x" not in emails
