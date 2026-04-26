"""Tests del endpoint GET /admin/asignaciones-recientes (R345 P1)."""
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


def _seed(db, campo, valor_anterior=None, valor_nuevo=None):
    db.add(AuditLogRecord(
        timestamp=ahora_utc(),
        usuario_email="x@x", accion="UPDATE",
        tabla="historial", campo=campo,
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
    ))
    db.commit()


class TestAsignacionesRecientes:
    def test_filtra_gestor_nombre(self, client, db_session):
        _seed(
            db_session, "gestor_nombre",
            valor_anterior="Alice", valor_nuevo="Bob",
        )
        _seed(
            db_session, "estado",
            valor_anterior="X", valor_nuevo="Y",
        )

        r = client.get("/admin/asignaciones-recientes")
        d = r.json()
        assert d["total_reasignaciones"] == 1
        assert d["items"][0]["valor_anterior"] == "Alice"
        assert d["items"][0]["valor_nuevo"] == "Bob"
