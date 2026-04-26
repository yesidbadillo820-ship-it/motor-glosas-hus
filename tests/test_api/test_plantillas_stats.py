"""Tests del endpoint GET /plantillas/stats (R159 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import PlantillaRecord, UsuarioRecord


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


def _seed(db, nombre="P", tipo="ARGUMENTO", eps="X", activa=1):
    db.add(PlantillaRecord(
        nombre=nombre, plantilla="<p>X</p>",
        tipo=tipo, eps=eps, activa=activa,
    ))
    db.commit()


class TestPlantillasStats:
    def test_estructura(self, client):
        r = client.get("/plantillas/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total", "activas", "inactivas",
                    "por_tipo", "top_10_eps"):
            assert key in d

    def test_counts_correctos(self, client, db_session):
        _seed(db_session, activa=1)
        _seed(db_session, activa=1)
        _seed(db_session, activa=0)
        r = client.get("/plantillas/stats")
        d = r.json()
        assert d["total"] == 3
        assert d["activas"] == 2
        assert d["inactivas"] == 1

    def test_por_tipo(self, client, db_session):
        _seed(db_session, tipo="ARGUMENTO")
        _seed(db_session, tipo="ARGUMENTO")
        _seed(db_session, tipo="DICTAMEN")
        r = client.get("/plantillas/stats")
        d = r.json()
        assert d["por_tipo"] == {"ARGUMENTO": 2, "DICTAMEN": 1}

    def test_top_10_eps_ordenado(self, client, db_session):
        for _ in range(3):
            _seed(db_session, eps="SANITAS")
        _seed(db_session, eps="OTRA")
        r = client.get("/plantillas/stats")
        d = r.json()
        assert d["top_10_eps"][0] == {
            "eps": "SANITAS", "plantillas": 3,
        }
