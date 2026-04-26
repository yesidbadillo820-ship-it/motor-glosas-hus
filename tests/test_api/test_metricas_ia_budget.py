"""Tests del endpoint GET /sistema/metricas-ia/budget (R125 P2)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AICallRecord, UsuarioRecord


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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, cost):
    db.add(AICallRecord(
        proveedor="anthropic", modelo="claude",
        cost_usd=cost,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestMetricasIaBudget:
    def test_estructura(self, client):
        r = client.get("/sistema/metricas-ia/budget")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("presupuesto_mensual_usd",
                    "gastado_usd_acumulado_mes",
                    "calls_acumuladas_mes",
                    "dias_transcurridos_mes",
                    "dias_totales_mes",
                    "proyeccion_fin_de_mes_usd",
                    "pct_consumido", "pct_proyectado",
                    "alerta", "mes_actual"):
            assert key in d
        assert d["alerta"] in ("GREEN", "YELLOW", "RED")

    def test_sin_gasto_alerta_green(self, client):
        r = client.get("/sistema/metricas-ia/budget?presupuesto_mensual_usd=100")
        d = r.json()
        assert d["gastado_usd_acumulado_mes"] == 0
        assert d["alerta"] == "GREEN"

    def test_acumula_costos_mes(self, client, db_session):
        _seed(db_session, cost=10.0)
        _seed(db_session, cost=15.5)
        r = client.get("/sistema/metricas-ia/budget?presupuesto_mensual_usd=100")
        d = r.json()
        assert d["gastado_usd_acumulado_mes"] == 25.5
        assert d["calls_acumuladas_mes"] == 2

    def test_proyeccion_lineal(self, client, db_session):
        # Si se gasta $50 en día 10 con presupuesto $100,
        # proyección = 50 * 30/10 = 150 (sobrepasa, RED)
        _seed(db_session, cost=50.0)
        r = client.get("/sistema/metricas-ia/budget?presupuesto_mensual_usd=100")
        d = r.json()
        # Proyección > 100 (puede variar según día actual)
        assert d["proyeccion_fin_de_mes_usd"] >= d["gastado_usd_acumulado_mes"]

    def test_alerta_red_si_excede_100(self, client, db_session):
        # Gastar muy por encima del presupuesto
        _seed(db_session, cost=200.0)
        r = client.get("/sistema/metricas-ia/budget?presupuesto_mensual_usd=100")
        d = r.json()
        # Ya gastamos 200% antes incluso de proyectar
        assert d["alerta"] == "RED"
        assert d["pct_proyectado"] >= 100
