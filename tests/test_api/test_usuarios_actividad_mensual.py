"""Tests del endpoint GET /admin/usuarios-actividad-mensual (R242 P1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, ts, usuario="alice@x"):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion="X", tabla="T",
        timestamp=ts,
    ))
    db.commit()


class TestUsuariosActividadMensual:
    def test_email_corto_400(self, client):
        r = client.get(
            "/admin/usuarios-actividad-mensual?usuario_email=A"
        )
        assert r.status_code == 400

    def test_serie_por_mes(self, client, db_session):
        _seed(db_session, ahora_utc())
        # Hace 60 días → fuera de ventana 6 meses (180d) → entra
        from datetime import timedelta
        _seed(db_session, ahora_utc() - timedelta(days=60))

        r = client.get(
            "/admin/usuarios-actividad-mensual"
            "?usuario_email=alice@x&meses=12"
        )
        d = r.json()
        assert d["total_eventos"] == 2
        assert len(d["serie"]) >= 1
