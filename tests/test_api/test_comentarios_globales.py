"""Tests del endpoint GET /glosas/stats/comentarios-globales (R160 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ComentarioGlosaRecord, UsuarioRecord


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


def _seed(db, glosa_id=1, autor="u@x", mencion=None, resuelto=0,
          dias_atras=1):
    db.add(ComentarioGlosaRecord(
        glosa_id=glosa_id, autor_email=autor,
        texto="x", mencion=mencion, resuelto=resuelto,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestComentariosGlobales:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/comentarios-globales")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_comentarios",
                    "glosas_con_comentarios", "menciones_totales",
                    "menciones_resueltas", "menciones_pendientes",
                    "top_5_comentaristas"):
            assert key in d

    def test_top_5_y_glosas_distintas(self, client, db_session):
        for _ in range(5):
            _seed(db_session, glosa_id=1, autor="alice@x")
        for _ in range(2):
            _seed(db_session, glosa_id=2, autor="bob@x")

        r = client.get("/glosas/stats/comentarios-globales")
        d = r.json()
        assert d["total_comentarios"] == 7
        assert d["glosas_con_comentarios"] == 2
        top = d["top_5_comentaristas"]
        assert top[0] == {"autor": "alice@x", "comentarios": 5}
        assert top[1] == {"autor": "bob@x", "comentarios": 2}

    def test_menciones_pendientes(self, client, db_session):
        _seed(db_session, mencion="resp@x", resuelto=1)
        _seed(db_session, mencion="resp@x", resuelto=0)
        _seed(db_session, mencion=None)  # no es mención

        r = client.get("/glosas/stats/comentarios-globales")
        d = r.json()
        assert d["menciones_totales"] == 2
        assert d["menciones_resueltas"] == 1
        assert d["menciones_pendientes"] == 1

    def test_excluye_fuera_ventana(self, client, db_session):
        _seed(db_session, dias_atras=5)
        _seed(db_session, dias_atras=60)
        r = client.get("/glosas/stats/comentarios-globales?dias=30")
        d = r.json()
        assert d["total_comentarios"] == 1
