"""Tests del endpoint GET /glosas/{id}/conciliaciones-resumen (R165 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ConciliacionRecord, GlosaRecord, UsuarioRecord


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


def _seed_conc(db, gid, **kw):
    base = dict(glosa_id=gid, creado_en=ahora_utc())
    base.update(kw)
    db.add(ConciliacionRecord(**base))
    db.commit()


class TestConciliacionesResumenGlosa:
    def test_404(self, client):
        r = client.get("/glosas/99999/conciliaciones-resumen")
        assert r.status_code == 404

    def test_glosa_sin_conciliaciones(self, client, db_session):
        _seed_glosa(db_session, 1)
        r = client.get("/glosas/1/conciliaciones-resumen")
        d = r.json()
        assert d["total"] == 0
        assert d["en_curso"] == 0
        assert d["items"] == []

    def test_resumen_con_conciliaciones(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_conc(db_session, 1,
                   estado_bilateral="PROGRAMADA",
                   valor_conciliado=5000)
        _seed_conc(db_session, 1,
                   estado_bilateral="ACTA_FIRMADA",
                   valor_conciliado=3000)

        r = client.get("/glosas/1/conciliaciones-resumen")
        d = r.json()
        assert d["total"] == 2
        assert d["en_curso"] == 1  # solo PROGRAMADA
        assert d["valor_conciliado_total"] == 8000

    def test_aislamiento_entre_glosas(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_conc(db_session, 1)
        _seed_conc(db_session, 2)
        _seed_conc(db_session, 2)

        r = client.get("/glosas/1/conciliaciones-resumen")
        d = r.json()
        assert d["total"] == 1
