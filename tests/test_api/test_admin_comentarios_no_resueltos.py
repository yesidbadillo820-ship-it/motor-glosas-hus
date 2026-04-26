"""Tests del endpoint GET /admin/comentarios-no-resueltos (R353 P1)."""
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


def _seed_glosa(db, glosa_id):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_com(db, glosa_id, resuelto=0, mencion=None):
    db.add(ComentarioGlosaRecord(
        glosa_id=glosa_id, autor_email="x", texto="t",
        resuelto=resuelto, mencion=mencion,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestComentariosNoResueltos:
    def test_filtra(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        # Glosa 1: 2 sin resolver
        _seed_com(db_session, 1, resuelto=0)
        _seed_com(db_session, 1, resuelto=0, mencion="x@x")
        # Glosa 2: 0 sin resolver
        _seed_com(db_session, 2, resuelto=1)

        r = client.get("/admin/comentarios-no-resueltos")
        d = r.json()
        assert d["total_glosas"] == 1
        assert d["items"][0]["glosa_id"] == 1
        assert d["items"][0]["comentarios_no_resueltos"] == 2
        assert d["items"][0]["menciones_pendientes"] == 1
