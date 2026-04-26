"""Tests del endpoint GET /glosas/stats/dashboard-snapshot (R109 P2)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestDashboardSnapshot:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/dashboard-snapshot")
        assert r.status_code == 200, r.text
        d = r.json()
        for sec in ("kpis", "economico", "resoluciones", "sla",
                    "generado_en"):
            assert sec in d

    def test_vacio(self, client):
        r = client.get("/glosas/stats/dashboard-snapshot")
        d = r.json()
        assert d["kpis"]["total"] == 0
        assert d["economico"]["valor_objetado_total"] == 0
        assert d["resoluciones"]["tasa_levantamiento_pct"] == 0.0

    def test_kpis_correctos(self, client, db_session):
        # 1 vencida, 1 critica, 1 en_tiempo, 1 cerrada
        _seed(db_session, dias_restantes=-5)
        _seed(db_session, dias_restantes=2)
        _seed(db_session, dias_restantes=15)
        _seed(db_session, estado="LEVANTADA")
        r = client.get("/glosas/stats/dashboard-snapshot")
        d = r.json()
        assert d["kpis"]["total"] == 4
        assert d["kpis"]["abiertas"] == 3
        assert d["kpis"]["cerradas"] == 1
        assert d["kpis"]["vencidas"] == 1
        assert d["kpis"]["criticas"] == 1
        assert d["kpis"]["en_tiempo"] == 1

    def test_economico(self, client, db_session):
        _seed(db_session, valor_objetado=10_000, valor_recuperado=5_000)
        _seed(db_session, valor_objetado=10_000, valor_recuperado=0)
        r = client.get("/glosas/stats/dashboard-snapshot")
        d = r.json()
        assert d["economico"]["valor_objetado_total"] == 20_000
        assert d["economico"]["valor_recuperado_total"] == 5_000
        # 5000/20000 = 25%
        assert d["economico"]["tasa_recuperacion_pct"] == 25.0

    def test_resoluciones(self, client, db_session):
        _seed(db_session, estado="LEVANTADA")
        _seed(db_session, estado="ACEPTADA")
        _seed(db_session, estado="RADICADA")  # no decidida
        r = client.get("/glosas/stats/dashboard-snapshot")
        d = r.json()
        assert d["resoluciones"]["decididas"] == 2
        assert d["resoluciones"]["levantadas"] == 1
        assert d["resoluciones"]["tasa_levantamiento_pct"] == 50.0
