"""Ronda 30 — regresiones de seguridad de la auditoría ultracode.

1. PATCH /usuarios/{id}/password y POST /usuarios/ exigían solo estar
   autenticado (get_usuario_actual): cualquier AUDITOR/VIEWER podía resetear
   la contraseña del SUPER_ADMIN o crear cuentas. Ahora exigen get_admin.
2. get_client_ip() lee cf-connecting-ip (IP real tras el Cloudflare Tunnel)
   y cae a get_remote_address si no está.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import UsuarioRecord


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(
        UsuarioRecord(
            id=1,
            email="root@hus.gov.co",
            rol="SUPER_ADMIN",
            activo=1,
            password_hash=get_password_hash("original"),
        )
    )
    s.add(
        UsuarioRecord(
            id=2,
            email="auditor@hus.gov.co",
            rol="AUDITOR",
            activo=1,
            password_hash=get_password_hash("auditorpw"),
        )
    )
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _client(db_session, usuario_actual):
    """Client que fija SOLO get_usuario_actual — get_admin corre de verdad."""
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_actual
    c = TestClient(app)
    return c, app


def _rol(db, email):
    return db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()


# ── #1 PATCH password requiere SUPER_ADMIN ───────────────────────────────


class TestResetPasswordSoloAdmin:
    def test_auditor_no_puede_resetear_password_ajena(self, db_session):
        auditor = _rol(db_session, "auditor@hus.gov.co")
        c, app = _client(db_session, auditor)
        try:
            hash_antes = _rol(db_session, "root@hus.gov.co").password_hash
            r = c.patch("/usuarios/1/password", json={"nueva_password": "hackeada99"})
            assert r.status_code == 403
            # el hash del SUPER_ADMIN NO cambió
            db_session.expire_all()
            assert _rol(db_session, "root@hus.gov.co").password_hash == hash_antes
        finally:
            app.dependency_overrides.clear()

    def test_super_admin_si_puede_resetear(self, db_session):
        root = _rol(db_session, "root@hus.gov.co")
        c, app = _client(db_session, root)
        try:
            r = c.patch("/usuarios/2/password", json={"nueva_password": "nuevapw12"})
            assert r.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ── #2 POST crear usuario requiere SUPER_ADMIN ───────────────────────────


class TestCrearUsuarioSoloAdmin:
    def test_auditor_no_puede_crear_usuario(self, db_session):
        auditor = _rol(db_session, "auditor@hus.gov.co")
        c, app = _client(db_session, auditor)
        try:
            r = c.post(
                "/usuarios/",
                json={"nombre": "Nuevo", "email": "nuevo@hus.gov.co", "password": "loquesea1"},
            )
            assert r.status_code == 403
            assert _rol(db_session, "nuevo@hus.gov.co") is None
        finally:
            app.dependency_overrides.clear()

    def test_super_admin_si_puede_crear(self, db_session):
        root = _rol(db_session, "root@hus.gov.co")
        c, app = _client(db_session, root)
        try:
            r = c.post(
                "/usuarios/",
                json={"nombre": "Nuevo Dos", "email": "nuevo2@hus.gov.co", "password": "loquesea1"},
            )
            assert r.status_code == 201
            assert _rol(db_session, "nuevo2@hus.gov.co") is not None
        finally:
            app.dependency_overrides.clear()


# ── #3 get_client_ip lee cf-connecting-ip ────────────────────────────────


class TestGetClientIP:
    def test_usa_cf_connecting_ip(self):
        from app.core.rate_limit import get_client_ip

        class _Req:
            def __init__(self, headers):
                self.headers = headers
                self.client = type("C", (), {"host": "10.0.0.5"})()

        req = _Req({"cf-connecting-ip": "181.49.20.7"})
        assert get_client_ip(req) == "181.49.20.7"

    def test_cae_a_remote_address_sin_header(self):
        from app.core.rate_limit import get_client_ip

        class _Req:
            def __init__(self):
                self.headers = {}
                self.client = type("C", (), {"host": "10.0.0.5"})()

        assert get_client_ip(_Req()) == "10.0.0.5"
