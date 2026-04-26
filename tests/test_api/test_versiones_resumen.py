"""Tests del endpoint GET /glosas/{id}/versiones-resumen (R129 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import DictamenVersionRecord, GlosaRecord, UsuarioRecord


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


def _seed_glosa(db, gid=1):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()
    return gid


def _seed_version(db, glosa_id, accion, autor, dias_atras=0):
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html="<p>x</p>",
        accion=accion,
        autor_email=autor,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestVersionesResumen:
    def test_404(self, client):
        r = client.get("/glosas/99999/versiones-resumen")
        assert r.status_code == 404

    def test_glosa_sin_versiones(self, client, db_session):
        gid = _seed_glosa(db_session)
        r = client.get(f"/glosas/{gid}/versiones-resumen")
        d = r.json()
        assert d["total_versiones"] == 0
        assert d["por_accion"] == {}
        assert d["ultima_accion"] is None

    def test_resumen_con_versiones(self, client, db_session):
        gid = _seed_glosa(db_session)
        _seed_version(db_session, gid, "CREAR", "alice@x", dias_atras=10)
        _seed_version(db_session, gid, "REFINAR", "alice@x", dias_atras=5)
        _seed_version(db_session, gid, "REFINAR", "bob@x", dias_atras=2)
        _seed_version(db_session, gid, "REGENERAR", "alice@x", dias_atras=1)

        r = client.get(f"/glosas/{gid}/versiones-resumen")
        d = r.json()
        assert d["total_versiones"] == 4
        assert d["por_accion"] == {
            "CREAR": 1, "REFINAR": 2, "REGENERAR": 1,
        }
        assert d["autores_distintos"] == ["alice@x", "bob@x"]
        assert d["ultima_accion"] == "REGENERAR"

    def test_aislamiento_entre_glosas(self, client, db_session):
        _seed_glosa(db_session, gid=1)
        _seed_glosa(db_session, gid=2)
        _seed_version(db_session, 1, "CREAR", "u@x")
        _seed_version(db_session, 2, "REFINAR", "u@x")
        _seed_version(db_session, 2, "REFINAR", "u@x")

        r = client.get("/glosas/1/versiones-resumen")
        d = r.json()
        assert d["total_versiones"] == 1
        assert d["por_accion"] == {"CREAR": 1}

        r2 = client.get("/glosas/2/versiones-resumen")
        d2 = r2.json()
        assert d2["total_versiones"] == 2
