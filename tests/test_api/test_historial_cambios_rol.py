"""Tests del endpoint GET /admin/historial-cambios-rol (R203 P1)."""
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


def _seed_audit(db, tabla, campo, anterior, nuevo, dias_atras=1):
    db.add(AuditLogRecord(
        usuario_email="actor@x", accion="UPDATE",
        tabla=tabla, registro_id=42,
        campo=campo, valor_anterior=anterior, valor_nuevo=nuevo,
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestHistorialCambiosRol:
    def test_estructura(self, client):
        r = client.get("/admin/historial-cambios-rol")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_cambios", "items"):
            assert key in d

    def test_filtra_solo_rol(self, client, db_session):
        # Cambio de rol → debe aparecer
        _seed_audit(db_session, "usuarios", "rol",
                    "AUDITOR", "SUPER_ADMIN")
        # Cambio de otro campo → NO
        _seed_audit(db_session, "usuarios", "nombre", "X", "Y")
        # Cambio de rol pero en otra tabla → NO
        _seed_audit(db_session, "glosas", "rol", "X", "Y")

        r = client.get("/admin/historial-cambios-rol")
        d = r.json()
        assert d["total_cambios"] == 1

    def test_metadata_correcta(self, client, db_session):
        _seed_audit(db_session, "usuarios", "rol",
                    "AUDITOR", "SUPER_ADMIN")
        r = client.get("/admin/historial-cambios-rol")
        d = r.json()
        item = d["items"][0]
        assert item["rol_anterior"] == "AUDITOR"
        assert item["rol_nuevo"] == "SUPER_ADMIN"
        assert item["usuario_afectado_id"] == 42
