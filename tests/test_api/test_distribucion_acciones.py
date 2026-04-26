"""Tests del endpoint GET /audit/distribucion-acciones (R154 P1)."""
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


def _seed(db, accion, dias_atras=1):
    db.add(AuditLogRecord(
        usuario_email="u@x", accion=accion, tabla="T",
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestDistribucionAcciones:
    def test_vacio(self, client):
        r = client.get("/audit/distribucion-acciones")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_eventos"] == 0
        assert d["items"] == []

    def test_distribucion_pct(self, client, db_session):
        # 6 UPDATE + 4 LOGIN = 10 total → 60%/40%
        for _ in range(6):
            _seed(db_session, "UPDATE")
        for _ in range(4):
            _seed(db_session, "LOGIN")

        r = client.get("/audit/distribucion-acciones")
        d = r.json()
        items = {it["accion"]: it for it in d["items"]}
        assert items["UPDATE"]["count"] == 6
        assert items["UPDATE"]["pct"] == 60.0
        assert items["LOGIN"]["count"] == 4
        assert items["LOGIN"]["pct"] == 40.0

    def test_orden_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "MUCHO")
        for _ in range(2):
            _seed(db_session, "POCO")
        r = client.get("/audit/distribucion-acciones")
        d = r.json()
        assert d["items"][0]["accion"] == "MUCHO"
        assert d["items"][1]["accion"] == "POCO"

    def test_excluye_fuera_ventana(self, client, db_session):
        _seed(db_session, "X", dias_atras=5)
        _seed(db_session, "X", dias_atras=60)
        r = client.get("/audit/distribucion-acciones?dias=30")
        d = r.json()
        assert d["total_eventos"] == 1
