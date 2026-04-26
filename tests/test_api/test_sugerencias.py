"""Tests del módulo de sugerencias / feedback in-app (R369)."""
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


@pytest.fixture
def auditor():
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
    )


@pytest.fixture
def admin():
    return UsuarioRecord(
        id=2, email="admin@hus.com", nombre="Admin",
        rol="SUPER_ADMIN", activo=1,
    )


def _client(db_session, user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: user
    return TestClient(app)


class TestSugerencias:
    def test_crear_y_listar_propias(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/sugerencias", json={
                "tipo": "BUG",
                "titulo": "El botón Guardar no funciona",
                "descripcion": "Al hacer click no pasa nada en Mis Glosas",
                "pagina": "/mis-glosas",
            })
            assert r.status_code == 201
            d = r.json()
            assert d["tipo"] == "BUG"
            assert d["estado"] == "ABIERTA"
            assert d["autor_email"] == "alice@hus.com"

            r2 = c.get("/sugerencias/yo")
            assert r2.status_code == 200
            assert r2.json()["total"] == 1
        from app.main import app
        app.dependency_overrides.clear()

    def test_tipo_invalido_400(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.post("/sugerencias", json={
                "tipo": "INVALIDO",
                "titulo": "test test",
                "descripcion": "descripcion suficiente",
            })
            assert r.status_code == 400
        from app.main import app
        app.dependency_overrides.clear()

    def test_admin_lista_y_triajea(self, db_session, auditor, admin):
        # Crear como auditor
        with _client(db_session, auditor) as c:
            r = c.post("/sugerencias", json={
                "tipo": "IDEA",
                "titulo": "Modo oscuro automático",
                "descripcion": "Que detecte la preferencia del SO",
            })
            sid = r.json()["id"]
        from app.main import app
        app.dependency_overrides.clear()

        # Admin lista y resuelve
        with _client(db_session, admin) as c:
            r = c.get("/admin/sugerencias")
            d = r.json()
            assert d["total"] == 1
            assert d["abiertas_global"] == 1

            r2 = c.put(f"/admin/sugerencias/{sid}", json={
                "estado": "RESUELTA",
                "nota_admin": "Implementado en build de hoy",
            })
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2["estado"] == "RESUELTA"
            assert d2["resuelto_por"] == "admin@hus.com"
        app.dependency_overrides.clear()

    def test_no_admin_no_lista_global(self, db_session, auditor):
        with _client(db_session, auditor) as c:
            r = c.get("/admin/sugerencias")
            assert r.status_code == 403
        from app.main import app
        app.dependency_overrides.clear()
