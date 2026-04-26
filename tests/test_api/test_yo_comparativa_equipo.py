"""Tests del endpoint GET /usuarios/yo/comparativa-equipo (R279 P1)."""
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
    return UsuarioRecord(
        id=1, email="alice@hus.com", nombre="Alice", rol="AUDITOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gestor, estado="LEVANTADA", recuperado=100):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestYoComparativaEquipo:
    def test_sin_datos(self, client):
        r = client.get("/usuarios/yo/comparativa-equipo")
        d = r.json()
        assert d["tu"]["decididas"] == 0
        assert d["equipo"]["total_gestores"] == 0

    def test_calcula_promedios(self, client, db_session):
        # Alice: 2 decididas, 2 LEV → 100% tasa, 200 rec
        _seed(db_session, "Alice", "LEVANTADA", recuperado=100)
        _seed(db_session, "Alice", "LEVANTADA", recuperado=100)
        # Bob: 2 decididas, 0 LEV → 0% tasa, 0 rec
        _seed(db_session, "Bob", "RATIFICADA", recuperado=0)
        _seed(db_session, "Bob", "RATIFICADA", recuperado=0)

        r = client.get("/usuarios/yo/comparativa-equipo")
        d = r.json()
        assert d["tu"]["decididas"] == 2
        assert d["tu"]["tasa_levantamiento_pct"] == 100.0
        assert d["tu"]["valor_recuperado_total"] == 200
        assert d["equipo"]["total_gestores"] == 2
        assert d["equipo"]["decididas_promedio"] == 2.0
        # Equipo: 2 LEV / 4 dec → 50%
        assert d["equipo"]["tasa_levantamiento_promedio_pct"] == 50.0
