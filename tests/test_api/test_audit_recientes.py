"""Tests del endpoint GET /admin/audit-recientes (R249 P1)."""
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


def _seed(db, hr_atras=1):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="X", tabla="T",
        timestamp=ahora_utc() - timedelta(hours=hr_atras),
    ))
    db.commit()


class TestAuditRecientes:
    def test_estructura(self, client):
        r = client.get("/admin/audit-recientes")
        d = r.json()
        for key in ("ventana_horas", "total", "items"):
            assert key in d

    def test_ventana(self, client, db_session):
        _seed(db_session, hr_atras=1)
        _seed(db_session, hr_atras=48)  # fuera

        r = client.get("/admin/audit-recientes?horas=24")
        d = r.json()
        assert d["total"] == 1

    def test_limit(self, client, db_session):
        for i in range(20):
            _seed(db_session, hr_atras=1)
        r = client.get("/admin/audit-recientes?limit=5")
        d = r.json()
        assert len(d["items"]) == 5
