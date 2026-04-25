"""Tests del endpoint /sistema/metricas-ia (R55 P2)."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import AICallRecord


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()


def _seed_call(db, **kw):
    base = dict(
        proveedor="anthropic", modelo="claude-sonnet-4-6",
        latency_ms=1000, input_tokens=100, cache_creation_input_tokens=0,
        cache_read_input_tokens=0, output_tokens=50, cost_usd=0.001,
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(AICallRecord(**base))
    db.commit()


class TestMetricasIaEndpoint:
    def test_sin_calls_retorna_ceros(self, db):
        from app.api.routers.sistema import metricas_ia
        user = MagicMock(rol="ADMIN")
        r = metricas_ia(dias=1, db=db, current_user=user)
        assert r["total_calls"] == 0
        assert r["cost_usd_total"] == 0.0
        assert r["por_modelo"] == []

    def test_agregaciones_basicas(self, db):
        from app.api.routers.sistema import metricas_ia
        # 3 calls: 2 sonnet, 1 haiku
        _seed_call(db, modelo="claude-sonnet-4-6", cost_usd=0.05, latency_ms=1000)
        _seed_call(db, modelo="claude-sonnet-4-6", cost_usd=0.03, latency_ms=2000)
        _seed_call(db, modelo="claude-haiku-4-5-20251001", cost_usd=0.001, latency_ms=500)
        user = MagicMock(rol="ADMIN")
        r = metricas_ia(dias=1, db=db, current_user=user)
        assert r["total_calls"] == 3
        assert abs(r["cost_usd_total"] - 0.081) < 0.001
        # 2 modelos
        assert len(r["por_modelo"]) == 2
        # Top por costo: sonnet primero
        assert r["por_modelo"][0]["modelo"] == "claude-sonnet-4-6"
        assert r["por_modelo"][0]["calls"] == 2

    def test_latencia_percentiles(self, db):
        from app.api.routers.sistema import metricas_ia
        for ms in [100, 200, 300, 400, 500, 1000, 2000, 3000, 4000, 9999]:
            _seed_call(db, latency_ms=ms)
        user = MagicMock(rol="ADMIN")
        r = metricas_ia(dias=1, db=db, current_user=user)
        assert r["latency_ms"]["max"] == 9999
        # p50 está en el medio (entre 400 y 500)
        assert 400 <= r["latency_ms"]["p50"] <= 1000
        # p95 cerca del top
        assert r["latency_ms"]["p95"] >= 4000

    def test_cache_hit_rate(self, db):
        from app.api.routers.sistema import metricas_ia
        # 2 calls: una sin cache, una con 90% cache_read
        _seed_call(db, input_tokens=1000, cache_read_input_tokens=0)
        _seed_call(db, input_tokens=100, cache_read_input_tokens=900)
        user = MagicMock(rol="ADMIN")
        r = metricas_ia(dias=1, db=db, current_user=user)
        # total_in = 2000, cache_read = 900 → 45%
        assert abs(r["cache_hit_rate_pct"] - 45.0) < 0.5

    def test_filtro_por_ventana(self, db):
        """Calls de hace 5 días no deben contar si dias=1."""
        from app.api.routers.sistema import metricas_ia
        _seed_call(db, creado_en=ahora_utc() - timedelta(days=5))
        _seed_call(db, creado_en=ahora_utc())
        user = MagicMock(rol="ADMIN")
        r = metricas_ia(dias=1, db=db, current_user=user)
        assert r["total_calls"] == 1
        # Pero con dias=7 deben verse los 2
        r7 = metricas_ia(dias=7, db=db, current_user=user)
        assert r7["total_calls"] == 2
