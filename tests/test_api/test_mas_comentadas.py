"""Tests del endpoint GET /glosas/stats/mas-comentadas (R196 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ComentarioGlosaRecord, GlosaRecord, UsuarioRecord,
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
def usuario():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_glosa(db, gid):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_com(db, gid, autor="u@x"):
    db.add(ComentarioGlosaRecord(
        glosa_id=gid, autor_email=autor,
        texto="x", creado_en=ahora_utc(),
    ))
    db.commit()


class TestMasComentadas:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/mas-comentadas")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("top_solicitado", "items"):
            assert key in d

    def test_orden_desc(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        for _ in range(5):
            _seed_com(db_session, 1)
        for _ in range(2):
            _seed_com(db_session, 2)

        r = client.get("/glosas/stats/mas-comentadas")
        d = r.json()
        assert d["items"][0]["glosa_id"] == 1
        assert d["items"][0]["n_comentarios"] == 5
        assert d["items"][1]["glosa_id"] == 2

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed_glosa(db_session, i + 1)
            _seed_com(db_session, i + 1)
        r = client.get("/glosas/stats/mas-comentadas?top=3")
        d = r.json()
        assert len(d["items"]) == 3
