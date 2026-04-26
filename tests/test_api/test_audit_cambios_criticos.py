"""Tests del endpoint GET /admin/audit-cambios-criticos (R341 P1)."""
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


def _seed(db, campo, usuario):
    db.add(AuditLogRecord(
        timestamp=ahora_utc(),
        usuario_email=usuario, accion="UPDATE",
        tabla="historial", campo=campo,
    ))
    db.commit()


class TestAuditCambiosCriticos:
    def test_filtra_campos_criticos(self, client, db_session):
        _seed(db_session, "estado", "alice@x")
        _seed(db_session, "estado", "alice@x")
        _seed(db_session, "valor_objetado", "bob@x")
        _seed(db_session, "campo_no_critico", "alice@x")

        r = client.get("/admin/audit-cambios-criticos")
        d = r.json()
        campos = {it["campo"]: it for it in d["items"]}
        assert campos["estado"]["count_cambios"] == 2
        assert campos["valor_objetado"]["count_cambios"] == 1
        assert "campo_no_critico" not in campos
