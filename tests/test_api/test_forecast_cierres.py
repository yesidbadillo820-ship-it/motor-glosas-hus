"""Tests del endpoint GET /glosas/stats/forecast-cierres (R115 P2)."""
from __future__ import annotations

from datetime import timedelta

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


def _seed_cerrada(db, dias_atras=15):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


def _seed_pendiente(db):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestForecastCierres:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/forecast-cierres")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["pendientes_inicial"] == 0
        assert d["velocidad_semanal_actual"] == 0
        # Serie tendrá entries con cierres=0 hasta cumplir semanas

    def test_velocidad_se_calcula(self, client, db_session):
        # 30 cerradas en últimos 30d → 1/d → 7/sem
        for _ in range(30):
            _seed_cerrada(db_session, dias_atras=15)
        r = client.get("/glosas/stats/forecast-cierres")
        d = r.json()
        assert d["velocidad_semanal_actual"] == 7.0

    def test_serie_decrementa_pendientes(self, client, db_session):
        # 30 cerradas/30d, 14 pendientes → 7/sem → 2 semanas
        for _ in range(30):
            _seed_cerrada(db_session, dias_atras=15)
        for _ in range(14):
            _seed_pendiente(db_session)
        r = client.get("/glosas/stats/forecast-cierres")
        d = r.json()
        assert d["pendientes_inicial"] == 14
        assert len(d["serie"]) == 2  # se cierra en 2 semanas
        assert d["serie"][0]["cierres_estimados"] == 7
        assert d["serie"][0]["pendientes_restantes_estimados"] == 7
        assert d["serie"][1]["pendientes_restantes_estimados"] == 0

    def test_sin_velocidad_serie_estancada(self, client, db_session):
        # Solo pendientes, sin histórico
        for _ in range(10):
            _seed_pendiente(db_session)
        r = client.get("/glosas/stats/forecast-cierres?semanas=3")
        d = r.json()
        # velocidad=0 → cierres siempre 0
        for w in d["serie"]:
            assert w["cierres_estimados"] == 0
            assert w["pendientes_restantes_estimados"] == 10
