"""Tests del endpoint GET /usuarios/stats (R164 P1)."""
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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1, email="coord@hus.gov.co",
        nombre="Coordinador", rol="COORDINADOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, email, rol="AUDITOR", activo=1, totp=None, nombre="X"):
    db.add(UsuarioRecord(
        email=email, rol=rol, activo=activo,
        nombre=nombre, totp_secret=totp,
        password_hash=get_password_hash("y"),
    ))
    db.commit()


class TestUsuariosStats:
    def test_estructura(self, client):
        r = client.get("/usuarios/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total", "activos", "inactivas" if False else
                    "inactivos", "con_2fa", "sin_nombre", "por_rol"):
            assert key in d

    def test_counts(self, client, db_session):
        _seed(db_session, "alice@x", activo=1, totp="ABC")
        _seed(db_session, "bob@x", activo=0)
        _seed(db_session, "carol@x", activo=1, nombre=None)

        r = client.get("/usuarios/stats")
        d = r.json()
        # 1 seed (coord activo) + 3 = 4
        assert d["total"] == 4
        # alice + carol + coord = 3 activos
        assert d["activos"] == 3
        # bob inactivo
        assert d["inactivos"] == 1
        # alice tiene 2FA
        assert d["con_2fa"] == 1
        # carol sin nombre
        assert d["sin_nombre"] == 1

    def test_por_rol(self, client, db_session):
        _seed(db_session, "a@x", rol="AUDITOR")
        _seed(db_session, "b@x", rol="AUDITOR")
        _seed(db_session, "c@x", rol="VIEWER")

        r = client.get("/usuarios/stats")
        d = r.json()
        # COORDINADOR del seed + AUDITOR×2 + VIEWER
        assert d["por_rol"]["AUDITOR"] == 2
        assert d["por_rol"]["VIEWER"] == 1
        assert d["por_rol"]["COORDINADOR"] == 1
