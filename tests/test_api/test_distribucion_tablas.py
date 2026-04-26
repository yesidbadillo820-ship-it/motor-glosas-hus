"""Tests del endpoint GET /audit/distribucion-tablas (R155 P1)."""
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
def usuario_coord(db_session):
    u = UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, tabla, dias_atras=1):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion="X", tabla=tabla,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestDistribucionTablas:
    def test_vacio(self, client):
        r = client.get("/audit/distribucion-tablas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_pct_correcto(self, client, db_session):
        # 7 glosas + 3 usuarios = 10 total → 70%/30%
        for _ in range(7):
            _seed(db_session, "glosas")
        for _ in range(3):
            _seed(db_session, "usuarios")
        r = client.get("/audit/distribucion-tablas")
        d = r.json()
        items = {it["tabla"]: it for it in d["items"]}
        assert items["glosas"]["pct"] == 70.0
        assert items["usuarios"]["pct"] == 30.0

    def test_orden_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "GRANDE")
        for _ in range(2):
            _seed(db_session, "PEQUEÑA")
        r = client.get("/audit/distribucion-tablas")
        d = r.json()
        assert d["items"][0]["tabla"] == "GRANDE"
        assert d["items"][1]["tabla"] == "PEQUEÑA"

    def test_excluye_tabla_null(self, client, db_session):
        # Evento con tabla=None NO debe aparecer
        db_session.add(AuditLogRecord(
            usuario_email="u@x", accion="X", tabla=None,
            timestamp=ahora_utc(),
        ))
        db_session.commit()
        r = client.get("/audit/distribucion-tablas")
        d = r.json()
        assert d["items"] == []
