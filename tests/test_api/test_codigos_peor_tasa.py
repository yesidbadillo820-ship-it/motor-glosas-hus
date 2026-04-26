"""Tests del endpoint GET /glosas/stats/codigos-peor-tasa (R229 P1)."""
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


def _seed(db, codigo, estado):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCodigosPeorTasa:
    def test_orden_asc(self, client, db_session):
        # MALO: 1 LEV / 5 → 20%
        _seed(db_session, "MALO", "LEVANTADA")
        for _ in range(4):
            _seed(db_session, "MALO", "ACEPTADA")
        # BUENO: 5 LEV → 100%
        for _ in range(5):
            _seed(db_session, "BUENO", "LEVANTADA")

        r = client.get("/glosas/stats/codigos-peor-tasa?min_decididas=1")
        d = r.json()
        # MALO primero
        assert d["items"][0]["codigo_glosa"] == "MALO"
        assert d["items"][0]["tasa_levantamiento_pct"] == 20.0
