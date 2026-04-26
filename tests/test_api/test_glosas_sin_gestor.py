"""Tests del endpoint GET /admin/glosas-sin-gestor (R271 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor=None, estado="RADICADA", valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestGlosasSinGestor:
    def test_lista_y_orden(self, client, db_session):
        _seed(db_session, gestor=None, valor=5_000_000)
        _seed(db_session, gestor="", valor=10_000_000)
        _seed(db_session, gestor="Alice", valor=999)  # tiene gestor
        _seed(db_session, gestor=None, valor=2_000_000)

        r = client.get("/admin/glosas-sin-gestor")
        d = r.json()
        assert d["total_sin_gestor"] == 3
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, gestor=None, estado="LEVANTADA", valor=999)
        r = client.get("/admin/glosas-sin-gestor")
        d = r.json()
        assert d["total_sin_gestor"] == 0

    def test_no_admin_403(self, db_session):
        from app.api.deps import get_usuario_actual
        from app.main import app
        no_admin = UsuarioRecord(
            id=99, email="x@x.com", rol="AUDITOR", activo=1,
        )
        app.dependency_overrides[get_db] = (
            lambda: iter([db_session]).__next__()
        )
        app.dependency_overrides[get_usuario_actual] = lambda: no_admin
        with TestClient(app) as c:
            r = c.get("/admin/glosas-sin-gestor")
            assert r.status_code == 403
        app.dependency_overrides.clear()
