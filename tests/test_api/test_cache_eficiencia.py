"""Tests del endpoint GET /sistema/metricas-ia/cache-eficiencia (R143 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AICacheRecord, AICallRecord, UsuarioRecord


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


def _seed_call(db, input_tok=1000, cache_read=0, cost=0.01):
    db.add(AICallRecord(
        proveedor="anthropic", modelo="claude",
        input_tokens=input_tok,
        cache_read_input_tokens=cache_read,
        cost_usd=cost, creado_en=ahora_utc(),
    ))
    db.commit()


class TestCacheEficiencia:
    def test_estructura(self, client):
        r = client.get("/sistema/metricas-ia/cache-eficiencia")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_calls", "total_input_tokens",
                    "total_cache_read_tokens", "hit_rate_pct",
                    "cost_total_usd", "ahorro_estimado_usd",
                    "ai_cache_filas_actuales"):
            assert key in d

    def test_sin_calls(self, client):
        r = client.get("/sistema/metricas-ia/cache-eficiencia")
        d = r.json()
        assert d["total_calls"] == 0
        assert d["hit_rate_pct"] == 0.0

    def test_hit_rate_calculado(self, client, db_session):
        # 1000 input + 500 cache_read → 50% hit rate
        _seed_call(db_session, input_tok=1000, cache_read=500)
        _seed_call(db_session, input_tok=1000, cache_read=500)

        r = client.get("/sistema/metricas-ia/cache-eficiencia")
        d = r.json()
        assert d["hit_rate_pct"] == 50.0
        assert d["total_input_tokens"] == 2000
        assert d["total_cache_read_tokens"] == 1000

    def test_ahorro_estimado_positivo(self, client, db_session):
        _seed_call(db_session, input_tok=1_000_000, cache_read=900_000)
        r = client.get("/sistema/metricas-ia/cache-eficiencia")
        d = r.json()
        # 900_000 × 0.9 × 3 / 1_000_000 = 2.43 USD
        assert d["ahorro_estimado_usd"] > 2.0

    def test_cuenta_cache_filas(self, client, db_session):
        for i in range(5):
            db_session.add(AICacheRecord(
                clave=f"x{i}" * 64, modelo="x",
                respuesta="r", hit_count=0,
                creado_en=ahora_utc(),
            ))
        db_session.commit()
        r = client.get("/sistema/metricas-ia/cache-eficiencia")
        d = r.json()
        assert d["ai_cache_filas_actuales"] == 5
