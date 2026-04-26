"""Tests del endpoint GET /glosas/stats/profesional-top (R258 P1)."""
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


def _seed(db, profesional, estado="RADICADA", valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        profesional_medico=profesional,
    ))
    db.commit()


class TestProfesionalTop:
    def test_excluye_sin_profesional(self, client, db_session):
        _seed(db_session, "Dr. House")
        _seed(db_session, None)
        _seed(db_session, "")
        r = client.get("/glosas/stats/profesional-top")
        d = r.json()
        assert d["total_profesionales"] == 1
        assert d["items"][0]["profesional_medico"] == "Dr. House"

    def test_orden_y_tasa(self, client, db_session):
        # Dr A: 3 glosas, 2 LEV / 2 decididas → 100%
        _seed(db_session, "Dr A", "LEVANTADA")
        _seed(db_session, "Dr A", "LEVANTADA")
        _seed(db_session, "Dr A", "RADICADA")
        # Dr B: 2 glosas, 1 LEV / 2 decididas → 50%
        _seed(db_session, "Dr B", "LEVANTADA")
        _seed(db_session, "Dr B", "RATIFICADA")

        r = client.get("/glosas/stats/profesional-top")
        d = r.json()
        # Ordenado por total_glosas DESC
        assert d["items"][0]["profesional_medico"] == "Dr A"
        assert d["items"][0]["total_glosas"] == 3
        assert d["items"][0]["decididas"] == 2
        assert d["items"][0]["tasa_levantamiento_pct"] == 100.0
        assert d["items"][1]["profesional_medico"] == "Dr B"
        assert d["items"][1]["tasa_levantamiento_pct"] == 50.0

    def test_limit(self, client, db_session):
        for i in range(5):
            _seed(db_session, f"Dr {i}")
        r = client.get("/glosas/stats/profesional-top?limit=2")
        d = r.json()
        assert len(d["items"]) == 2
        assert d["total_profesionales"] == 5
