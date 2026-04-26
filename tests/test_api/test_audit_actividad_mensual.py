"""Tests del endpoint GET /admin/audit-actividad-mensual (R272 P1)."""
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


def _seed(db, accion, usuario, dias_atras=0):
    db.add(AuditLogRecord(
        timestamp=ahora_utc() - timedelta(days=dias_atras),
        usuario_email=usuario,
        accion=accion,
        tabla="historial",
    ))
    db.commit()


class TestAuditActividadMensual:
    def test_serie_mensual(self, client, db_session):
        _seed(db_session, "UPDATE", "alice@x.com", dias_atras=2)
        _seed(db_session, "UPDATE", "alice@x.com", dias_atras=5)
        _seed(db_session, "DELETE", "bob@x.com", dias_atras=1)

        r = client.get("/admin/audit-actividad-mensual?meses=3")
        d = r.json()
        assert d["ventana_meses"] == 3
        # Todos los eventos en el mes actual
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["total_eventos"] == 3
        assert mes["usuarios_distintos"] == 2

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
            r = c.get("/admin/audit-actividad-mensual")
            assert r.status_code == 403
        app.dependency_overrides.clear()
