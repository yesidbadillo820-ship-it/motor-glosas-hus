"""Tests del endpoint GET /admin/heatmap-usuario (R188 P1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord


def _lunes_pasado():
    """Lunes de la semana pasada (7-13 días atrás), a las 00:00.

    Se usa en vez de una fecha fija para que los tests no caduquen cuando esa
    fecha se sale de la ventana de días que consulta el endpoint.
    """
    ahora = ahora_utc()
    return (ahora - timedelta(days=ahora.weekday() + 7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


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
        id=1,
        email="root@hus.gov.co",
        rol="SUPER_ADMIN",
        activo=1,
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


def _seed(db, usuario, ts):
    db.add(
        AuditLogRecord(
            usuario_email=usuario,
            accion="X",
            tabla="T",
            timestamp=ts,
        )
    )
    db.commit()


class TestHeatmapUsuario:
    def test_usuario_corto_400(self, client):
        r = client.get("/admin/heatmap-usuario?usuario_email=A")
        assert r.status_code == 400

    def test_usuario_sin_eventos(self, client):
        r = client.get("/admin/heatmap-usuario?usuario_email=ghost@x")
        d = r.json()
        assert d["total_eventos"] == 0

    def test_filtra_por_usuario(self, client, db_session):
        lunes = _lunes_pasado()
        _seed(db_session, "alice@x", lunes.replace(hour=10))
        _seed(db_session, "bob@x", lunes.replace(hour=10))

        r = client.get("/admin/heatmap-usuario?usuario_email=alice@x&dias=120")
        d = r.json()
        assert d["total_eventos"] == 1
