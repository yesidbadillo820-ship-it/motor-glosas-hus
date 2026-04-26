"""Tests del endpoint GET /admin/audit-cleanup-recomendado (R202 P1)."""
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


def _seed(db, dias_atras=1):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="X", tabla="T",
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAuditCleanup:
    def test_estructura(self, client):
        r = client.get("/admin/audit-cleanup-recomendado")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("dias_retencion", "fecha_corte",
                    "eventos_total", "eventos_a_purgar",
                    "bytes_estimados_ahorro",
                    "mb_estimados_ahorro"):
            assert key in d

    def test_eventos_a_purgar(self, client, db_session):
        # 3 dentro de retención + 2 fuera
        _seed(db_session, dias_atras=10)
        _seed(db_session, dias_atras=20)
        _seed(db_session, dias_atras=100)
        _seed(db_session, dias_atras=400)
        _seed(db_session, dias_atras=500)

        r = client.get("/admin/audit-cleanup-recomendado?dias_retencion=365")
        d = r.json()
        assert d["eventos_total"] == 5
        assert d["eventos_a_purgar"] == 2  # 400 y 500 días
