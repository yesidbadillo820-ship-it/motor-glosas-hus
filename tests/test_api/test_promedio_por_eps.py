"""Tests del endpoint GET /glosas/stats/promedio-por-eps (R152 P1)."""
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


def _seed(db, eps, valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestPromedioPorEPS:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/promedio-por-eps?min_glosas=1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_promedio_y_mediano(self, client, db_session):
        _seed(db_session, "SANITAS", valor=100)
        _seed(db_session, "SANITAS", valor=200)
        _seed(db_session, "SANITAS", valor=300)
        # Promedio = 200, mediano = 200, max = 300
        r = client.get("/glosas/stats/promedio-por-eps?min_glosas=1")
        d = r.json()
        item = d["items"][0]
        assert item["eps"] == "SANITAS"
        assert item["count"] == 3
        assert item["valor_promedio"] == 200.0
        assert item["valor_mediano"] == 200.0
        assert item["valor_max"] == 300

    def test_orden_promedio_desc(self, client, db_session):
        # GRANDE: 1M promedio
        _seed(db_session, "GRANDE", valor=1_000_000)
        _seed(db_session, "GRANDE", valor=1_000_000)
        _seed(db_session, "GRANDE", valor=1_000_000)
        # CHICA: 1k promedio
        _seed(db_session, "CHICA", valor=1_000)
        _seed(db_session, "CHICA", valor=1_000)
        _seed(db_session, "CHICA", valor=1_000)

        r = client.get("/glosas/stats/promedio-por-eps")
        d = r.json()
        assert d["items"][0]["eps"] == "GRANDE"
        assert d["items"][1]["eps"] == "CHICA"

    def test_filtra_min_glosas(self, client, db_session):
        # Solo 2 → no aparece con min_glosas=3
        _seed(db_session, "POCAS", valor=100)
        _seed(db_session, "POCAS", valor=200)
        r = client.get("/glosas/stats/promedio-por-eps?min_glosas=3")
        d = r.json()
        assert d["items"] == []
