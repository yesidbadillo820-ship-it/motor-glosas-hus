"""Tests del endpoint GET /glosas/{id}/comentarios-resumen (R161 P1)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed_com(db, gid, autor, mencion=None, resuelto=0, dias_atras=1):
    db.add(ComentarioGlosaRecord(
        glosa_id=gid, autor_email=autor,
        texto="x", mencion=mencion, resuelto=resuelto,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestComentariosResumenGlosa:
    def test_404(self, client):
        r = client.get("/glosas/99999/comentarios-resumen")
        assert r.status_code == 404

    def test_glosa_sin_comentarios(self, client, db_session):
        _seed_glosa(db_session, 1)
        r = client.get("/glosas/1/comentarios-resumen")
        d = r.json()
        assert d["total_comentarios"] == 0
        assert d["autores_distintos"] == []
        assert d["ultimo_comentario_en"] is None

    def test_resumen_basico(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_com(db_session, 1, "alice@x")
        _seed_com(db_session, 1, "bob@x", mencion="resp@x", resuelto=0)
        _seed_com(db_session, 1, "alice@x", mencion="resp@x", resuelto=1)

        r = client.get("/glosas/1/comentarios-resumen")
        d = r.json()
        assert d["total_comentarios"] == 3
        assert d["autores_distintos"] == ["alice@x", "bob@x"]
        # Solo 1 mención pendiente
        assert d["menciones_pendientes"] == 1
        assert d["ultimo_comentario_en"] is not None

    def test_aislamiento_entre_glosas(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_com(db_session, 1, "u@x")
        _seed_com(db_session, 2, "u@x")
        _seed_com(db_session, 2, "u@x")

        r = client.get("/glosas/1/comentarios-resumen")
        d = r.json()
        assert d["total_comentarios"] == 1
