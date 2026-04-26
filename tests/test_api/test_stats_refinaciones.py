"""Tests del endpoint GET /glosas/stats/refinaciones (R129 P2)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import DictamenVersionRecord, UsuarioRecord


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


def _seed(db, glosa_id, accion, autor, dias_atras=1):
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id, dictamen_html="<p>x</p>",
        accion=accion, autor_email=autor,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestStatsRefinaciones:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/refinaciones")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_acciones"] == 0
        assert d["por_accion"] == {}

    def test_agrega_acciones(self, client, db_session):
        _seed(db_session, 1, "CREAR", "alice@x")
        _seed(db_session, 1, "REFINAR", "alice@x")
        _seed(db_session, 2, "REFINAR", "bob@x")
        _seed(db_session, 2, "REGENERAR", "bob@x")

        r = client.get("/glosas/stats/refinaciones")
        d = r.json()
        assert d["total_acciones"] == 4
        assert d["por_accion"]["REFINAR"] == 2
        assert d["por_accion"]["CREAR"] == 1
        assert d["por_accion"]["REGENERAR"] == 1
        assert d["glosas_con_refinaciones"] == 2

    def test_top_5_autores(self, client, db_session):
        for _ in range(5):
            _seed(db_session, 1, "REFINAR", "alice@x")
        for _ in range(2):
            _seed(db_session, 1, "REFINAR", "bob@x")

        r = client.get("/glosas/stats/refinaciones")
        d = r.json()
        assert d["top_5_autores"][0] == {"autor": "alice@x", "acciones": 5}
        assert d["top_5_autores"][1] == {"autor": "bob@x", "acciones": 2}

    def test_promedio_versiones_por_glosa(self, client, db_session):
        # Glosa 1: 3 versiones, glosa 2: 1 versión → promedio = 2
        for _ in range(3):
            _seed(db_session, 1, "REFINAR", "u@x")
        _seed(db_session, 2, "CREAR", "u@x")
        r = client.get("/glosas/stats/refinaciones")
        d = r.json()
        assert d["promedio_versiones_por_glosa"] == 2.0

    def test_tasa_refinacion(self, client, db_session):
        # 4 REFINAR / 5 total = 80%
        for _ in range(4):
            _seed(db_session, 1, "REFINAR", "u@x")
        _seed(db_session, 1, "CREAR", "u@x")
        r = client.get("/glosas/stats/refinaciones")
        d = r.json()
        assert d["tasa_refinacion_pct"] == 80.0

    def test_excluye_fuera_ventana(self, client, db_session):
        _seed(db_session, 1, "REFINAR", "u@x", dias_atras=5)
        _seed(db_session, 1, "REFINAR", "u@x", dias_atras=60)
        r = client.get("/glosas/stats/refinaciones?dias=30")
        d = r.json()
        assert d["total_acciones"] == 1
