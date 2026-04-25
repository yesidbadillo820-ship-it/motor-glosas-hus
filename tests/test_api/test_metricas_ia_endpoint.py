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


class TestMetricasIaPorGlosa:
    def test_glosa_sin_calls(self, db):
        from app.api.routers.sistema import metricas_ia_por_glosa
        user = MagicMock(rol="ADMIN")
        r = metricas_ia_por_glosa(glosa_id=999, db=db, current_user=user)
        assert r["total_calls"] == 0
        assert r["calls"] == []

    def test_glosa_con_un_call(self, db):
        from app.api.routers.sistema import metricas_ia_por_glosa
        _seed_call(db, glosa_id=42, cost_usd=0.025, latency_ms=2000)
        # Otra glosa para confirmar aislamiento
        _seed_call(db, glosa_id=43, cost_usd=0.999)
        user = MagicMock(rol="ADMIN")
        r = metricas_ia_por_glosa(glosa_id=42, db=db, current_user=user)
        assert r["total_calls"] == 1
        assert r["cost_usd_total"] == 0.025
        assert r["calls"][0]["latency_ms"] == 2000

    def test_glosa_con_multiples_calls_orden_cronologico(self, db):
        """Debe ordenar por creado_en ASC (call inicial primero)."""
        from app.api.routers.sistema import metricas_ia_por_glosa
        _seed_call(db, glosa_id=7, cost_usd=0.05, creado_en=ahora_utc() - timedelta(seconds=20))
        _seed_call(db, glosa_id=7, cost_usd=0.03, creado_en=ahora_utc() - timedelta(seconds=10))
        _seed_call(db, glosa_id=7, cost_usd=0.001, creado_en=ahora_utc())
        user = MagicMock(rol="ADMIN")
        r = metricas_ia_por_glosa(glosa_id=7, db=db, current_user=user)
        assert r["total_calls"] == 3
        # cost_usd_total = 0.081
        assert abs(r["cost_usd_total"] - 0.081) < 0.001
        # Orden cronológico: el primero tiene el cost más alto (0.05)
        assert r["calls"][0]["cost_usd"] == 0.05


class TestMetricasIaPorUsuario:
    def test_ranking_por_costo_descendente(self, db):
        from app.api.routers.sistema import metricas_ia_por_usuario
        # Usuario A gasta más
        _seed_call(db, user_email="A@hus.com", cost_usd=0.10)
        _seed_call(db, user_email="A@hus.com", cost_usd=0.05)
        # Usuario B gasta menos
        _seed_call(db, user_email="B@hus.com", cost_usd=0.01)
        # Usuario sin email se excluye
        _seed_call(db, user_email=None, cost_usd=999)

        user = MagicMock(rol="ADMIN")
        r = metricas_ia_por_usuario(dias=7, db=db, current_user=user)
        assert r["total_usuarios"] == 2
        assert r["ranking"][0]["user_email"] == "A@hus.com"
        assert r["ranking"][0]["calls"] == 2
        assert abs(r["ranking"][0]["cost_usd"] - 0.15) < 0.001
        assert r["ranking"][1]["user_email"] == "B@hus.com"

    def test_promedio_latencia_por_usuario(self, db):
        from app.api.routers.sistema import metricas_ia_por_usuario
        _seed_call(db, user_email="C@hus.com", latency_ms=1000, cost_usd=0.01)
        _seed_call(db, user_email="C@hus.com", latency_ms=3000, cost_usd=0.01)
        user = MagicMock(rol="ADMIN")
        r = metricas_ia_por_usuario(dias=7, db=db, current_user=user)
        # promedio = 2000
        assert r["ranking"][0]["latency_ms_promedio"] == 2000

    def test_filtro_ventana_dias(self, db):
        from app.api.routers.sistema import metricas_ia_por_usuario
        _seed_call(
            db, user_email="X@hus.com", cost_usd=0.10,
            creado_en=ahora_utc() - timedelta(days=10),
        )
        _seed_call(db, user_email="X@hus.com", cost_usd=0.01)
        user = MagicMock(rol="ADMIN")
        # Con dias=7, el call de hace 10 días no debe contar
        r = metricas_ia_por_usuario(dias=7, db=db, current_user=user)
        assert r["ranking"][0]["calls"] == 1
