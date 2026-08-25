"""Tests del endpoint GET /admin/heatmap-usuario (R188 P1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
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
        # La fecha va relativa a hoy, no clavada en el calendario. Estaba
        # escrita 20-04-2026 con ventana de 120 días: el 18-08-2026 el evento
        # salió de la ventana por unas horas y la prueba empezó a fallar sola,
        # sin que nadie tocara el código.
        hace_un_mes = datetime.now(timezone.utc) - timedelta(days=30)
        _seed(db_session, "alice@x", hace_un_mes)
        _seed(db_session, "bob@x", hace_un_mes)

        r = client.get("/admin/heatmap-usuario?usuario_email=alice@x&dias=120")
        d = r.json()
        assert d["total_eventos"] == 1
