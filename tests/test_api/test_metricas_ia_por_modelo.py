"""Tests del endpoint GET /sistema/metricas-ia/por-modelo (R125 P1)."""
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


def _seed(db, proveedor, modelo, cost=0.01, latency=500,
          input_tok=1000, output_tok=500, cache_read=0, dias_atras=5):
    db.add(AICallRecord(
        proveedor=proveedor, modelo=modelo,
        latency_ms=latency, cost_usd=cost,
        input_tokens=input_tok, output_tokens=output_tok,
        cache_read_input_tokens=cache_read,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestMetricasIaPorModelo:
    def test_vacio(self, client):
        r = client.get("/sistema/metricas-ia/por-modelo")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["calls_totales"] == 0

    def test_agrupa_por_modelo(self, client, db_session):
        _seed(db_session, "anthropic", "claude-sonnet-4-6")
        _seed(db_session, "anthropic", "claude-sonnet-4-6")
        _seed(db_session, "groq", "llama-3.3-70b")

        r = client.get("/sistema/metricas-ia/por-modelo")
        d = r.json()
        modelos = {it["modelo"]: it for it in d["items"]}
        assert modelos["claude-sonnet-4-6"]["calls"] == 2
        assert modelos["llama-3.3-70b"]["calls"] == 1

    def test_acumula_costo_y_tokens(self, client, db_session):
        _seed(db_session, "anthropic", "X", cost=0.05,
              input_tok=1000, output_tok=500)
        _seed(db_session, "anthropic", "X", cost=0.03,
              input_tok=2000, output_tok=200)
        r = client.get("/sistema/metricas-ia/por-modelo")
        d = r.json()
        item = d["items"][0]
        assert item["cost_usd_total"] == 0.08
        assert item["tokens_input"] == 3000
        assert item["tokens_output"] == 700

    def test_latency_promedio(self, client, db_session):
        _seed(db_session, "anthropic", "X", latency=200)
        _seed(db_session, "anthropic", "X", latency=400)
        r = client.get("/sistema/metricas-ia/por-modelo")
        d = r.json()
        # Promedio = 300
        assert d["items"][0]["latency_promedio_ms"] == 300

    def test_cache_hit_rate(self, client, db_session):
        # 1000 input + 500 cache_read → cache_hit = 50%
        _seed(db_session, "anthropic", "X",
              input_tok=1000, cache_read=500)
        r = client.get("/sistema/metricas-ia/por-modelo")
        d = r.json()
        assert d["items"][0]["cache_hit_rate_pct"] == 50.0

    def test_orden_por_cost_desc(self, client, db_session):
        _seed(db_session, "anthropic", "CARO", cost=1.00)
        _seed(db_session, "groq", "BARATO", cost=0.001)
        r = client.get("/sistema/metricas-ia/por-modelo")
        d = r.json()
        assert d["items"][0]["modelo"] == "CARO"
        assert d["items"][1]["modelo"] == "BARATO"

    def test_excluye_fuera_de_ventana(self, client, db_session):
        _seed(db_session, "anthropic", "X", dias_atras=5)   # dentro
        _seed(db_session, "anthropic", "X", dias_atras=60)  # fuera (default 30)
        r = client.get("/sistema/metricas-ia/por-modelo")
        d = r.json()
        assert d["calls_totales"] == 1
