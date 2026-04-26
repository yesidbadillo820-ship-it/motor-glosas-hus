"""Tests del endpoint GET /admin/usuarios-sin-glosas (R156 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


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


def _seed_user(db, email, nombre, rol="AUDITOR", activo=1):
    db.add(UsuarioRecord(
        email=email, nombre=nombre, rol=rol, activo=activo,
        password_hash=get_password_hash("y"),
    ))
    db.commit()


def _seed_glosa(db, gestor, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestUsuariosSinGlosas:
    def test_estructura(self, client):
        r = client.get("/admin/usuarios-sin-glosas")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_usuarios_activos_evaluados",
                    "total_sin_glosas_asignadas", "items"):
            assert key in d

    def test_detecta_usuario_sin_carga(self, client, db_session):
        _seed_user(db_session, "alice@x", "Alice")
        _seed_user(db_session, "bob@x", "Bob")
        _seed_glosa(db_session, "Alice")  # solo Alice tiene carga

        r = client.get("/admin/usuarios-sin-glosas")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "bob@x" in emails
        assert "alice@x" not in emails

    def test_no_cuenta_glosas_cerradas(self, client, db_session):
        _seed_user(db_session, "alice@x", "Alice")
        # Solo glosa cerrada → Alice tiene cuenta sin carga ABIERTA
        _seed_glosa(db_session, "Alice", estado="LEVANTADA")
        r = client.get("/admin/usuarios-sin-glosas")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "alice@x" in emails

    def test_excluye_inactivos(self, client, db_session):
        _seed_user(db_session, "off@x", "Off", activo=0)
        r = client.get("/admin/usuarios-sin-glosas")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "off@x" not in emails

    def test_excluye_super_admin(self, client, db_session):
        # El root del fixture es SUPER_ADMIN → no debe aparecer
        r = client.get("/admin/usuarios-sin-glosas")
        d = r.json()
        emails = [it["email"] for it in d["items"]]
        assert "root@hus.gov.co" not in emails
