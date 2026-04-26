"""Tests del endpoint GET /admin/usuarios-inactivos (R98 P2)."""
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
        id=1, email="root@hus.gov.co", nombre="Root", rol="SUPER_ADMIN",
        activo=1, password_hash=get_password_hash("xxxx"),
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


def _seed_user(db, id, email, activo=1):
    db.add(UsuarioRecord(
        id=id, email=email, nombre=email.split("@")[0],
        rol="AUDITOR", activo=activo,
        password_hash=get_password_hash("x"),
    ))
    db.commit()


def _seed_audit(db, email, dias_atras):
    db.add(AuditLogRecord(
        usuario_email=email, accion="X", tabla="T",
        timestamp=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestUsuariosInactivos:
    def test_solo_root_sin_actividad(self, client):
        # Solo el SUPER_ADMIN seed sin eventos
        r = client.get("/admin/usuarios-inactivos")
        assert r.status_code == 200, r.text
        d = r.json()
        # root@hus.gov.co es activo y no tiene eventos
        assert d["total_inactivos"] == 1
        assert d["items"][0]["email"] == "root@hus.gov.co"
        assert d["items"][0]["dias_sin_actividad"] is None

    def test_usuario_con_actividad_reciente_excluido(self, client, db_session):
        _seed_user(db_session, 2, "alice@x")
        _seed_audit(db_session, "alice@x", dias_atras=10)  # reciente
        r = client.get("/admin/usuarios-inactivos")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "alice@x" not in emails

    def test_usuario_con_actividad_vieja_incluido(self, client, db_session):
        _seed_user(db_session, 2, "alice@x")
        _seed_audit(db_session, "alice@x", dias_atras=120)  # vieja
        r = client.get("/admin/usuarios-inactivos")
        d = r.json()
        alice = next(it for it in d["items"] if it["email"] == "alice@x")
        assert alice["dias_sin_actividad"] == 120

    def test_usuario_inactivo_excluido(self, client, db_session):
        # Usuario marcado activo=0 NO debe aparecer en el listado
        _seed_user(db_session, 2, "deactivada@x", activo=0)
        r = client.get("/admin/usuarios-inactivos")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "deactivada@x" not in emails

    def test_umbral_custom(self, client, db_session):
        _seed_user(db_session, 2, "alice@x")
        _seed_audit(db_session, "alice@x", dias_atras=20)  # 20d sin actividad
        # Con dias=10 (umbral), Alice está inactiva
        r = client.get("/admin/usuarios-inactivos?dias=10")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "alice@x" in emails
        # Con dias=30, ya tiene actividad reciente
        r = client.get("/admin/usuarios-inactivos?dias=30")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "alice@x" not in emails

    def test_orden_mas_inactivos_primero(self, client, db_session):
        _seed_user(db_session, 2, "alice@x")
        _seed_user(db_session, 3, "bob@x")
        _seed_audit(db_session, "alice@x", dias_atras=200)
        _seed_audit(db_session, "bob@x", dias_atras=100)
        r = client.get("/admin/usuarios-inactivos")
        d = r.json()
        items = [it for it in d["items"] if it["email"] in {"alice@x", "bob@x"}]
        # Alice (200d) antes que Bob (100d)
        assert items[0]["email"] == "alice@x"
        assert items[1]["email"] == "bob@x"
