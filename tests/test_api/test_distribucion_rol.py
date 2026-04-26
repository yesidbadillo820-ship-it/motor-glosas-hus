"""Tests del endpoint GET /admin/distribucion-rol (R266 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestDistribucionRol:
    def test_basico(self, client, db_session):
        db_session.add(UsuarioRecord(
            id=10, email="a@x.com", rol="AUDITOR", activo=1,
        ))
        db_session.add(UsuarioRecord(
            id=11, email="b@x.com", rol="AUDITOR", activo=0,
        ))
        db_session.add(UsuarioRecord(
            id=12, email="c@x.com", rol="COORDINADOR", activo=1,
        ))
        db_session.commit()

        r = client.get("/admin/distribucion-rol")
        d = r.json()
        # admin_user es fixture in-memory, no está en la DB
        roles = {it["rol"]: it for it in d["items"]}
        assert roles["AUDITOR"]["total"] == 2
        assert roles["AUDITOR"]["activos"] == 1
        assert roles["AUDITOR"]["inactivos"] == 1
        assert roles["COORDINADOR"]["total"] == 1
        assert d["total_usuarios"] == 3
        assert d["total_activos"] == 2

    def test_no_admin_403(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        no_admin = UsuarioRecord(
            id=99, email="x@x.com", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: no_admin
        with TestClient(app) as c:
            r = c.get("/admin/distribucion-rol")
            assert r.status_code == 403
        app.dependency_overrides.clear()
