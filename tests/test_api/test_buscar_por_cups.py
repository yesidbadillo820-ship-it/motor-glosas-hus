"""Tests del endpoint GET /glosas/buscar-por-cups (R186 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ConceptoGlosaRecord, GlosaRecord, UsuarioRecord,
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


def _seed_concepto(db, gid, cups):
    db.add(ConceptoGlosaRecord(
        glosa_id=gid, codigo_glosa="TA",
        cups_codigo=cups, valor_objetado=500,
    ))
    db.commit()


class TestBuscarPorCUPS:
    def test_cups_inexistente(self, client):
        r = client.get("/glosas/buscar-por-cups?cups=999999")
        d = r.json()
        assert d["encontradas"] == 0
        assert d["items"] == []

    def test_match_exacto(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_concepto(db_session, 1, "906625")
        _seed_concepto(db_session, 2, "OTRO")

        r = client.get("/glosas/buscar-por-cups?cups=906625")
        d = r.json()
        assert d["encontradas"] == 1
        assert d["items"][0]["id"] == 1

    def test_distinct_glosa(self, client, db_session):
        # Una glosa con 2 conceptos del mismo CUPS → debe aparecer 1 vez
        _seed_glosa(db_session, 1)
        _seed_concepto(db_session, 1, "906625")
        _seed_concepto(db_session, 1, "906625")

        r = client.get("/glosas/buscar-por-cups?cups=906625")
        d = r.json()
        assert d["encontradas"] == 1
        assert len(d["items"]) == 1
