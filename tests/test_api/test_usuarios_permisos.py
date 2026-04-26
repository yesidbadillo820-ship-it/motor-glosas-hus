"""Tests del endpoint /usuarios/yo/permisos (R76 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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


def _client(db_session, rol):
    from app.api.deps import get_usuario_actual
    from app.main import app
    user = UsuarioRecord(id=1, email=f"{rol.lower()}@hus.com", rol=rol, activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: user
    return TestClient(app)


class TestPermisos:
    def test_super_admin_puede_todo(self, db_session):
        with _client(db_session, "SUPER_ADMIN") as c:
            r = c.get("/usuarios/yo/permisos")
            d = r.json()
            p = d["permisos"]
            # SUPER_ADMIN tiene todos los flags True
            for k in p:
                assert p[k] is True, f"SUPER_ADMIN debería poder {k}"

    def test_auditor_no_puede_admin(self, db_session):
        with _client(db_session, "AUDITOR") as c:
            r = c.get("/usuarios/yo/permisos")
            d = r.json()
            p = d["permisos"]
            # Auditor NO debe poder backup ni purgar
            assert p["puede_descargar_backup_db"] is False
            assert p["puede_purgar_mantenimiento"] is False
            assert p["puede_admin_usuarios"] is False
            # Pero sí puede análisis
            assert p["puede_analizar_glosa"] is True
            assert p["puede_refinar_dictamen"] is True

    def test_coordinador_no_admin(self, db_session):
        with _client(db_session, "COORDINADOR") as c:
            r = c.get("/usuarios/yo/permisos")
            p = r.json()["permisos"]
            # Coordinador puede dashboard team y métricas
            assert p["puede_ver_metricas_ia"] is True
            assert p["puede_ver_dashboard_equipo"] is True
            # Pero NO backup ni admin usuarios
            assert p["puede_descargar_backup_db"] is False
            assert p["puede_admin_usuarios"] is False

    def test_viewer_basicos(self, db_session):
        with _client(db_session, "VIEWER") as c:
            r = c.get("/usuarios/yo/permisos")
            p = r.json()["permisos"]
            # Viewer puede analizar (es la operación base)
            assert p["puede_analizar_glosa"] is True
            # Pero NO puede destructivos
            assert p["puede_eliminar_glosa"] is False
            assert p["puede_bulk_mover_papelera"] is False

    def test_estructura_completa(self, db_session):
        with _client(db_session, "ADMIN") as c:
            r = c.get("/usuarios/yo/permisos")
            d = r.json()
            assert d["usuario_email"] == "admin@hus.com"
            assert d["rol"] == "ADMIN"
            assert isinstance(d["permisos"], dict)
            assert len(d["permisos"]) >= 10
