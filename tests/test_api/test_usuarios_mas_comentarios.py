"""Tests del endpoint GET /admin/usuarios-mas-comentarios (R294 P1)."""
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


def _seed_com(db, glosa_id, autor, mencion=None, resuelto=0):
    db.add(ComentarioGlosaRecord(
        glosa_id=glosa_id, autor_email=autor, texto="t",
        mencion=mencion, resuelto=resuelto,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestUsuariosMasComentarios:
    def test_ranking(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        for _ in range(3):
            _seed_com(db_session, 1, "alice@x")
        _seed_com(db_session, 2, "alice@x", mencion="bob@x")
        _seed_com(db_session, 1, "bob@x", resuelto=1)

        r = client.get("/admin/usuarios-mas-comentarios")
        d = r.json()
        # Alice debe ser primera (4 comentarios)
        assert d["items"][0]["autor_email"] == "alice@x"
        assert d["items"][0]["total_comentarios"] == 4
        assert d["items"][0]["menciones_emitidas"] == 1
        assert d["items"][0]["glosas_distintas"] == 2

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
            r = c.get("/admin/usuarios-mas-comentarios")
            assert r.status_code == 403
        app.dependency_overrides.clear()
