"""Tests del endpoint GET /glosas/stats/glosas-sin-comentarios (R284 P1)."""
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


def _seed_glosa(db, glosa_id, estado="RADICADA", valor=1000):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_comentario(db, glosa_id):
    db.add(ComentarioGlosaRecord(
        glosa_id=glosa_id, autor_email="x", texto="t",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestGlosasSinComentarios:
    def test_filtra_con_comentario(self, client, db_session):
        _seed_glosa(db_session, 1, valor=5000)
        _seed_glosa(db_session, 2, valor=3000)
        _seed_comentario(db_session, 2)
        # Glosa 1 sin comentario, glosa 2 con comentario

        r = client.get("/glosas/stats/glosas-sin-comentarios")
        d = r.json()
        assert d["total_sin_comentarios"] == 1
        assert d["items"][0]["glosa_id"] == 1

    def test_excluye_cerradas(self, client, db_session):
        _seed_glosa(db_session, 1, estado="LEVANTADA")
        r = client.get("/glosas/stats/glosas-sin-comentarios")
        d = r.json()
        assert d["total_sin_comentarios"] == 0

    def test_orden_desc(self, client, db_session):
        _seed_glosa(db_session, 1, valor=100)
        _seed_glosa(db_session, 2, valor=999)
        r = client.get("/glosas/stats/glosas-sin-comentarios")
        d = r.json()
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
