"""Tests del endpoint GET /admin/usuarios-actividad-resumen (R346 P1)."""
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


def _seed(db, usuario, accion, tabla="historial"):
    db.add(AuditLogRecord(
        timestamp=ahora_utc(),
        usuario_email=usuario, accion=accion, tabla=tabla,
    ))
    db.commit()


class TestUsuariosActividadResumen:
    def test_ranking(self, client, db_session):
        _seed(db_session, "alice@x", "UPDATE")
        _seed(db_session, "alice@x", "UPDATE")
        _seed(db_session, "alice@x", "INSERT")
        _seed(db_session, "bob@x", "DELETE")

        r = client.get("/admin/usuarios-actividad-resumen")
        d = r.json()
        b = {it["usuario_email"]: it for it in d["items"]}
        assert b["alice@x"]["count_total"] == 3
        assert b["alice@x"]["acciones"]["UPDATE"] == 2
        assert b["alice@x"]["acciones"]["INSERT"] == 1
        assert b["bob@x"]["count_total"] == 1
