"""Tests del endpoint GET /glosas/stats/glosas-conciliadas-detalle (R344 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
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


def _seed_glosa(db, glosa_id, valor):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concil(db, glosa_id, valor):
    db.add(ConciliacionRecord(
        glosa_id=glosa_id, valor_conciliado=valor,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestGlosasConciliadasDetalle:
    def test_lista_solo_con_concil(self, client, db_session):
        _seed_glosa(db_session, 1, valor=10000)
        _seed_glosa(db_session, 2, valor=5000)
        # Solo glosa 1 tiene conciliación
        _seed_concil(db_session, 1, valor=8000)
        _seed_concil(db_session, 1, valor=2000)

        r = client.get("/glosas/stats/glosas-conciliadas-detalle")
        d = r.json()
        assert d["total"] == 1
        assert d["items"][0]["glosa_id"] == 1
        assert d["items"][0]["valor_conciliado_total"] == 10000

    def test_vacio(self, client):
        r = client.get("/glosas/stats/glosas-conciliadas-detalle")
        d = r.json()
        assert d["total"] == 0
