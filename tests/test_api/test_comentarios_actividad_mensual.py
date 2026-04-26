"""Tests del endpoint GET /glosas/stats/comentarios-actividad-mensual (R276 P1)."""
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


def _seed_glosa(db, glosa_id):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_comentario(db, glosa_id, autor, mencion=None, resuelto=0):
    db.add(ComentarioGlosaRecord(
        glosa_id=glosa_id, autor_email=autor, texto="t",
        mencion=mencion, resuelto=resuelto,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestComentariosActividadMensual:
    def test_serie(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_comentario(db_session, 1, "alice@x.com")
        _seed_comentario(db_session, 1, "bob@x.com", mencion="alice@x.com")
        _seed_comentario(db_session, 1, "alice@x.com", resuelto=1)

        r = client.get(
            "/glosas/stats/comentarios-actividad-mensual?meses=2"
        )
        d = r.json()
        assert len(d["serie"]) == 1
        mes = d["serie"][0]
        assert mes["count_comentarios"] == 3
        assert mes["autores_distintos"] == 2
        assert mes["menciones"] == 1
        assert mes["resueltos"] == 1

    def test_vacio(self, client):
        r = client.get(
            "/glosas/stats/comentarios-actividad-mensual"
        )
        d = r.json()
        assert d["serie"] == []
