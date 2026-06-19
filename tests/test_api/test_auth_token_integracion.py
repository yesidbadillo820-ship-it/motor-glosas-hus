"""Tests del endpoint POST /auth/token-integracion (jump-box soportes).

Contexto: el token de login normal expira en 8h, lo que rompe un agente
24/7 como tools/jumpbox_sync.py. Este endpoint emite un token de larga
duración (hasta 730 días) para una cuenta de servicio con rol AUDITOR+.
Solo SUPER_ADMIN puede emitirlo.
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
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _client(db_session, admin_rol="SUPER_ADMIN"):
    """Cliente autenticado como `admin_rol`, con un usuario de servicio
    jumpbox (AUDITOR, activo) ya sembrado en la BD."""
    from app.api.deps import get_usuario_actual
    from app.main import app

    admin = UsuarioRecord(
        id=1,
        email="admin@hus.com",
        nombre="Admin",
        rol=admin_rol,
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    jumpbox = UsuarioRecord(
        id=2,
        email="jumpbox.hus@sinacsc.com",
        nombre="Jump-box Soportes",
        rol="AUDITOR",
        activo=1,
        password_hash=get_password_hash("yyyy"),
    )
    db_session.add_all([admin, jumpbox])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin
    return TestClient(app)


class TestTokenIntegracion:
    def test_super_admin_emite_token(self, db_session):
        with _client(db_session) as c:
            r = c.post(
                "/auth/token-integracion",
                data={"email": "jumpbox.hus@sinacsc.com", "dias": 365},
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["access_token"]
            assert d["token_type"] == "bearer"
            assert d["email"] == "jumpbox.hus@sinacsc.com"
            assert d["rol"] == "AUDITOR"
            assert d["expira_en_dias"] == 365

    def test_dias_se_topa_en_730(self, db_session):
        with _client(db_session) as c:
            r = c.post(
                "/auth/token-integracion",
                data={"email": "jumpbox.hus@sinacsc.com", "dias": 99999},
            )
            assert r.status_code == 200, r.text
            assert r.json()["expira_en_dias"] == 730

    def test_email_inexistente_404(self, db_session):
        with _client(db_session) as c:
            r = c.post(
                "/auth/token-integracion",
                data={"email": "noexiste@hus.com", "dias": 30},
            )
            assert r.status_code == 404

    def test_cuenta_desactivada_400(self, db_session):
        # _client siembra admin (id=1) + jumpbox (id=2) y configura overrides.
        with _client(db_session) as c:
            # Desactivar el jumpbox antes de pedir token
            jb = db_session.query(UsuarioRecord).filter_by(id=2).first()
            jb.activo = 0
            db_session.commit()
            r = c.post(
                "/auth/token-integracion",
                data={"email": "jumpbox.hus@sinacsc.com", "dias": 30},
            )
            assert r.status_code == 400

    def test_rol_viewer_rechazado(self, db_session):
        """Una cuenta VIEWER no puede subir soportes → token denegado."""
        from app.api.deps import get_usuario_actual
        from app.main import app

        viewer = UsuarioRecord(
            id=3,
            email="viewer@hus.com",
            nombre="Viewer",
            rol="VIEWER",
            activo=1,
            password_hash=get_password_hash("zzzz"),
        )
        admin = UsuarioRecord(
            id=1,
            email="admin@hus.com",
            nombre="Admin",
            rol="SUPER_ADMIN",
            activo=1,
            password_hash=get_password_hash("xxxx"),
        )
        db_session.add_all([admin, viewer])
        db_session.commit()
        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: admin
        with TestClient(app) as c:
            r = c.post(
                "/auth/token-integracion",
                data={"email": "viewer@hus.com", "dias": 30},
            )
            assert r.status_code == 400
            assert "AUDITOR" in r.json()["detail"]
            app.dependency_overrides.clear()

    def test_no_admin_rechazado(self, db_session):
        """Un AUDITOR no puede emitir tokens de integración (solo SUPER_ADMIN)."""
        with _client(db_session, admin_rol="AUDITOR") as c:
            r = c.post(
                "/auth/token-integracion",
                data={"email": "jumpbox.hus@sinacsc.com", "dias": 30},
            )
            assert r.status_code == 403
