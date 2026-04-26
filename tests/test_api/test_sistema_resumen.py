"""Tests del endpoint GET /admin/sistema-resumen (R281 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ComentarioGlosaRecord,
    ConciliacionRecord,
    GlosaRecord,
    UsuarioRecord,
)


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


def _seed_glosa(db, glosa_id, estado="RADICADA"):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestSistemaResumen:
    def test_resumen(self, client, db_session):
        _seed_glosa(db_session, 1, estado="RADICADA")
        _seed_glosa(db_session, 2, estado="LEVANTADA")
        db_session.add(UsuarioRecord(
            id=10, email="x@x.com", rol="AUDITOR", activo=1,
        ))
        db_session.add(ComentarioGlosaRecord(
            glosa_id=1, autor_email="x", texto="t",
            creado_en=ahora_utc(),
        ))
        db_session.add(ConciliacionRecord(
            glosa_id=2, resultado="OK",
            creado_en=ahora_utc(),
        ))
        db_session.commit()

        r = client.get("/admin/sistema-resumen")
        d = r.json()
        assert d["glosas"]["total"] == 2
        assert d["glosas"]["abiertas"] == 1
        assert d["glosas"]["cerradas"] == 1
        # admin_user no está en DB, solo el seed user
        assert d["usuarios"]["total"] == 1
        assert d["comentarios"] == 1
        assert d["conciliaciones"] == 1

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
            r = c.get("/admin/sistema-resumen")
            assert r.status_code == 403
        app.dependency_overrides.clear()
