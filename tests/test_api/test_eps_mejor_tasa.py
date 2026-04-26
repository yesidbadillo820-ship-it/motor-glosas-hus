"""Tests del endpoint GET /glosas/stats/eps-mejor-tasa (R227 P1)."""
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


def _seed(db, eps, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSMejorTasa:
    def test_orden_desc(self, client, db_session):
        # GANADORA: 5 LEV / 5 → 100%
        for _ in range(5):
            _seed(db_session, "GANADORA", "LEVANTADA")
        # MEDIA: 3 LEV / 5 → 60%
        for _ in range(3):
            _seed(db_session, "MEDIA", "LEVANTADA")
        for _ in range(2):
            _seed(db_session, "MEDIA", "ACEPTADA")

        r = client.get("/glosas/stats/eps-mejor-tasa?min_decididas=1")
        d = r.json()
        assert d["items"][0]["eps"] == "GANADORA"
        assert d["items"][0]["tasa_levantamiento_pct"] == 100.0
        assert d["items"][1]["eps"] == "MEDIA"

    def test_filtro_min_decididas(self, client, db_session):
        # Solo 2 LEV, min=5 → no aparece
        _seed(db_session, "POCAS", "LEVANTADA")
        _seed(db_session, "POCAS", "LEVANTADA")
        r = client.get("/glosas/stats/eps-mejor-tasa?min_decididas=5")
        d = r.json()
        assert d["items"] == []
