"""Tests del endpoint POST /auth/refresh (R82 P1)."""
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


def _client_para(db_session, activo=True, rol="AUDITOR"):
    from app.api.deps import get_usuario_actual
    from app.main import app
    u = UsuarioRecord(
        id=1, email="x@hus.com", nombre="Test", rol=rol,
        activo=int(activo),
        password_hash=get_password_hash("xxxx"),
    )
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    return TestClient(app), u


class TestRefreshToken:
    def test_devuelve_nuevo_token(self, db_session):
        with _client_para(db_session)[0] as c:
            r = c.post("/auth/refresh")
            assert r.status_code == 200, r.text
            d = r.json()
            assert "access_token" in d
            assert d["token_type"] == "bearer"
            assert d["rol"] == "AUDITOR"

    def test_usuario_inactivo_401(self, db_session):
        with _client_para(db_session, activo=False)[0] as c:
            r = c.post("/auth/refresh")
            assert r.status_code == 401

    def test_token_es_distinto_al_input(self, db_session):
        """Cada refresh genera nuevo token (con nuevo exp)."""
        import time
        with _client_para(db_session)[0] as c:
            r1 = c.post("/auth/refresh")
            t1 = r1.json()["access_token"]
            time.sleep(1)
            r2 = c.post("/auth/refresh")
            t2 = r2.json()["access_token"]
            # Tokens distintos por timestamp
            assert t1 != t2
