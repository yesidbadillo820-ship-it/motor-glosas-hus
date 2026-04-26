"""Tests del endpoint GET /sistema/auth-stats (R240 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord


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


def _seed(db, accion):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion=accion, tabla="auth",
        timestamp=ahora_utc(),
    ))
    db.commit()


class TestAuthStats:
    def test_estructura(self, client):
        r = client.get("/sistema/auth-stats")
        d = r.json()
        for key in ("ventana_dias", "contadores"):
            assert key in d
        for k in ("login_ok", "login_fail", "logout",
                  "twofa", "refresh"):
            assert k in d["contadores"]

    def test_clasifica_acciones(self, client, db_session):
        _seed(db_session, "AUTH-OK")
        _seed(db_session, "AUTH-OK")
        _seed(db_session, "AUTH-FAIL")
        _seed(db_session, "AUTH-LOGOUT")
        _seed(db_session, "AUTH-2FA")

        r = client.get("/sistema/auth-stats")
        d = r.json()
        c = d["contadores"]
        assert c["login_ok"] == 2
        assert c["login_fail"] == 1
        assert c["logout"] == 1
        assert c["twofa"] == 1
