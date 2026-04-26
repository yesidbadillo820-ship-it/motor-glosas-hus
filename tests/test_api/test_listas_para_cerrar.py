"""Tests del endpoint GET /glosas/stats/listas-para-cerrar (R194 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        dictamen="x" * 300,
        codigo_respuesta="RE9901",
        gestor_nombre="Alice",
        dias_restantes=5,
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestListasParaCerrar:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/listas-para-cerrar")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_listas", "items"):
            assert key in d

    def test_glosa_completa_aparece(self, client, db_session):
        _seed(db_session)
        r = client.get("/glosas/stats/listas-para-cerrar")
        d = r.json()
        assert d["total_listas"] == 1

    def test_excluye_dictamen_corto(self, client, db_session):
        _seed(db_session, dictamen="x" * 50)  # <200
        r = client.get("/glosas/stats/listas-para-cerrar")
        d = r.json()
        assert d["items"] == []

    def test_excluye_sin_codigo_respuesta(self, client, db_session):
        _seed(db_session, codigo_respuesta=None)
        r = client.get("/glosas/stats/listas-para-cerrar")
        d = r.json()
        assert d["items"] == []

    def test_excluye_sin_gestor(self, client, db_session):
        _seed(db_session, gestor_nombre=None)
        r = client.get("/glosas/stats/listas-para-cerrar")
        d = r.json()
        assert d["items"] == []

    def test_excluye_estado_no_radicada(self, client, db_session):
        _seed(db_session, estado="LEVANTADA")
        r = client.get("/glosas/stats/listas-para-cerrar")
        d = r.json()
        assert d["items"] == []

    def test_orden_por_dias_restantes(self, client, db_session):
        _seed(db_session, dias_restantes=10)
        _seed(db_session, dias_restantes=2)
        _seed(db_session, dias_restantes=5)
        r = client.get("/glosas/stats/listas-para-cerrar")
        d = r.json()
        dias = [it["dias_restantes"] for it in d["items"]]
        assert dias == [2, 5, 10]
