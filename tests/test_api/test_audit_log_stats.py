"""Tests del endpoint GET /admin/audit-log-stats (R326 P1)."""
from __future__ import annotations

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


def _seed(db, accion):
    db.add(AuditLogRecord(
        timestamp=ahora_utc(),
        usuario_email="x", accion=accion, tabla="historial",
    ))
    db.commit()


class TestAuditLogStats:
    def test_distribucion(self, client, db_session):
        _seed(db_session, "UPDATE")
        _seed(db_session, "UPDATE")
        _seed(db_session, "INSERT")

        r = client.get("/admin/audit-log-stats")
        d = r.json()
        assert d["total_eventos"] == 3
        b = {it["accion"]: it for it in d["items"]}
        assert b["UPDATE"]["count"] == 2
        assert b["UPDATE"]["pct"] == round(200 / 3, 2)
        assert b["INSERT"]["count"] == 1
