"""Tests del endpoint GET /glosas/stats/analizadas-hoy (R174 P1)."""
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


def _seed(db, glosa_id, accion, autor, dias_atras=0):
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id, dictamen_html="<p>X</p>",
        accion=accion, autor_email=autor,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestAnalizadasHoy:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/analizadas-hoy")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("fecha", "dictamenes_hoy",
                    "glosas_distintas_hoy",
                    "por_accion", "top_5_autores"):
            assert key in d

    def test_solo_cuenta_hoy(self, client, db_session):
        # Hoy
        _seed(db_session, 1, "CREAR", "u@x", dias_atras=0)
        # Hace 2 días → no
        _seed(db_session, 2, "CREAR", "u@x", dias_atras=2)

        r = client.get("/glosas/stats/analizadas-hoy")
        d = r.json()
        assert d["dictamenes_hoy"] == 1
        assert d["glosas_distintas_hoy"] == 1

    def test_por_accion_y_top_autores(self, client, db_session):
        _seed(db_session, 1, "CREAR", "alice@x")
        _seed(db_session, 1, "REFINAR", "alice@x")
        _seed(db_session, 2, "REFINAR", "bob@x")

        r = client.get("/glosas/stats/analizadas-hoy")
        d = r.json()
        assert d["por_accion"]["REFINAR"] == 2
        assert d["por_accion"]["CREAR"] == 1
        assert d["glosas_distintas_hoy"] == 2
        # Alice tiene 2 acciones
        assert d["top_5_autores"][0] == {
            "autor": "alice@x", "acciones": 2,
        }
