"""Tests del endpoint GET /glosas/{id}/conceptos-resumen (R139 P2)."""
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


def _seed_concepto(db, gid, **kw):
    base = dict(
        glosa_id=gid, codigo_glosa="TA0201",
        valor_objetado=500, factura="F-1",
    )
    base.update(kw)
    db.add(ConceptoGlosaRecord(**base))
    db.commit()


class TestConceptosResumen:
    def test_404(self, client):
        r = client.get("/glosas/99999/conceptos-resumen")
        assert r.status_code == 404

    def test_glosa_sin_conceptos(self, client, db_session):
        _seed_glosa(db_session, 1)
        r = client.get("/glosas/1/conceptos-resumen")
        d = r.json()
        assert d["total_conceptos"] == 0
        assert d["valor_objetado_conceptos"] == 0

    def test_resumen_basico(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_concepto(db_session, 1, valor_objetado=1000,
                       codigo_glosa="TA0201")
        _seed_concepto(db_session, 1, valor_objetado=500,
                       codigo_glosa="TA0201")
        _seed_concepto(db_session, 1, valor_objetado=2000,
                       codigo_glosa="FA0603",
                       dictamen_html="<p>" + "x" * 100 + "</p>")

        r = client.get("/glosas/1/conceptos-resumen")
        d = r.json()
        assert d["total_conceptos"] == 3
        assert d["valor_objetado_conceptos"] == 3500
        assert d["respondidos"] == 1
        assert d["pendientes"] == 2
        assert d["por_codigo_glosa"] == {"TA0201": 2, "FA0603": 1}

    def test_centros_costo_distintos(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_concepto(db_session, 1, centro_costo="LAB")
        _seed_concepto(db_session, 1, centro_costo="LAB")
        _seed_concepto(db_session, 1, centro_costo="QUIROFANO")

        r = client.get("/glosas/1/conceptos-resumen")
        d = r.json()
        assert d["centros_costo_distintos"] == ["LAB", "QUIROFANO"]

    def test_aislamiento_entre_glosas(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_concepto(db_session, 1, valor_objetado=999)
        _seed_concepto(db_session, 2, valor_objetado=1)

        r = client.get("/glosas/1/conceptos-resumen")
        d = r.json()
        assert d["total_conceptos"] == 1
        assert d["valor_objetado_conceptos"] == 999
