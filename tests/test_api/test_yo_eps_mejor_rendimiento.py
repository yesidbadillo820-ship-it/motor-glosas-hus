"""Tests del endpoint GET /usuarios/yo/eps-mejor-rendimiento (R337 P1)."""
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


def _seed(db, gestor, eps, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    ))
    db.commit()


class TestYoEPSMejorRendimiento:
    def test_orden(self, client, db_session):
        # Alice con SANITAS: 3 LEV / 3 → 100%
        for _ in range(3):
            _seed(db_session, "Alice", "SANITAS")
        # Alice con OTRA: 1 LEV / 3 → 33%
        _seed(db_session, "Alice", "OTRA", estado="LEVANTADA")
        _seed(db_session, "Alice", "OTRA", estado="RATIFICADA")
        _seed(db_session, "Alice", "OTRA", estado="RATIFICADA")

        r = client.get(
            "/usuarios/yo/eps-mejor-rendimiento?min_decididas=1"
        )
        d = r.json()
        # SANITAS primero (100%)
        assert d["items"][0]["eps"] == "SANITAS"
        assert d["items"][0]["tasa_levantamiento_pct"] == 100.0

    def test_min_decididas(self, client, db_session):
        _seed(db_session, "Alice", "POCAS")
        r = client.get(
            "/usuarios/yo/eps-mejor-rendimiento?min_decididas=5"
        )
        d = r.json()
        assert d["items"] == []
