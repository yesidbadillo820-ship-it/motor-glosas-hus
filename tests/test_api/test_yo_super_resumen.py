"""Tests del endpoint GET /usuarios/yo/super-resumen (R397 P1)."""
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
        id=1, email="alice@hus.com", nombre="Alice",
        rol="AUDITOR", activo=1,
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


def _seed(db, gestor="Alice", dias=10, estado="RADICADA",
          recuperado=0, decidida=False):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
        dias_restantes=dias,
        fecha_decision_eps=ahora_utc() if decidida else None,
    ))
    db.commit()


class TestSuperResumen:
    def test_estructura(self, client):
        r = client.get("/usuarios/yo/super-resumen")
        d = r.json()
        for k in (
            "kpis", "donut", "alertas_count",
            "menciones_pendientes", "streak_actual",
        ):
            assert k in d
        for k in (
            "abiertas", "vencidas", "criticas",
            "decididas_mes", "levantadas_mes",
            "recuperado_mes", "tasa_levantamiento_mes_pct",
        ):
            assert k in d["kpis"]

    def test_kpis(self, client, db_session):
        _seed(db_session, dias=-5)
        _seed(db_session, dias=2)
        _seed(db_session, dias=10)
        _seed(
            db_session, estado="LEVANTADA",
            recuperado=500, decidida=True,
        )
        r = client.get("/usuarios/yo/super-resumen")
        d = r.json()
        assert d["kpis"]["abiertas"] == 3
        assert d["kpis"]["vencidas"] == 1
        assert d["kpis"]["criticas"] == 1
        assert d["kpis"]["decididas_mes"] == 1
