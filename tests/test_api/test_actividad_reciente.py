"""Tests del endpoint GET /admin/actividad-reciente (R110 P2)."""
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


def _seed_audit(db, usuario, accion, tabla, segundos_atras=0):
    db.add(AuditLogRecord(
        usuario_email=usuario, accion=accion, tabla=tabla,
        registro_id=1,
        timestamp=ahora_utc() - timedelta(seconds=segundos_atras),
    ))
    db.commit()


class TestActividadReciente:
    def test_vacio(self, client):
        r = client.get("/admin/actividad-reciente")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_devueltos"] == 0
        assert d["items"] == []

    def test_lista_eventos_audit(self, client, db_session):
        _seed_audit(db_session, "alice@x", "UPDATE", "glosas")
        _seed_audit(db_session, "bob@x", "DELETE", "usuarios")
        r = client.get("/admin/actividad-reciente")
        d = r.json()
        assert d["total_devueltos"] == 2
        assert all(it["tipo"] == "AUDIT" for it in d["items"])

    def test_orden_descendente_por_timestamp(self, client, db_session):
        _seed_audit(db_session, "u@x", "X", "T", segundos_atras=100)
        _seed_audit(db_session, "u@x", "Y", "T", segundos_atras=10)
        _seed_audit(db_session, "u@x", "Z", "T", segundos_atras=50)
        r = client.get("/admin/actividad-reciente")
        d = r.json()
        timestamps = [it["timestamp"] for it in d["items"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_limit_respetado(self, client, db_session):
        for i in range(20):
            _seed_audit(db_session, "u@x", f"A{i}", "T",
                        segundos_atras=i * 5)
        r = client.get("/admin/actividad-reciente?limit=5")
        d = r.json()
        assert d["total_devueltos"] == 5
        assert d["limit"] == 5

    def test_estructura_item(self, client, db_session):
        _seed_audit(db_session, "u@x", "UPDATE", "glosas")
        r = client.get("/admin/actividad-reciente")
        d = r.json()
        for it in d["items"]:
            for key in ("timestamp", "tipo", "usuario",
                        "descripcion", "id_evento"):
                assert key in it
            assert it["tipo"] in ("AUDIT", "AI_CALL")
