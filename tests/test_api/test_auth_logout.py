"""Tests del endpoint POST /auth/logout (R82 P2)."""
from __future__ import annotations

import logging

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
def usuario():
    return UsuarioRecord(
        id=1, email="auditor@hus.com", rol="AUDITOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestAuthLogout:
    def test_logout_devuelve_ok(self, client):
        r = client.post("/auth/logout")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True

    def test_logout_se_logea_para_auditoria(self, client, caplog):
        caplog.set_level(logging.INFO, logger="motor_glosas")
        client.post("/auth/logout")
        msgs = " ".join(r.getMessage() for r in caplog.records)
        assert "AUTH-LOGOUT" in msgs
        assert "auditor@hus.com" in msgs
