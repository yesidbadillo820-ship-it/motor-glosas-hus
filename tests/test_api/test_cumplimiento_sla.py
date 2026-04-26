"""Tests del endpoint GET /glosas/stats/cumplimiento-sla (R90 P1)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestCumplimientoSLA:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cumplimiento-sla")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 0
        assert d["vencidas"] == 0
        assert d["criticas"] == 0
        assert d["en_tiempo"] == 0
        assert d["cerradas"] == 0
        assert d["tasa_cumplimiento_pct"] == 0.0
        assert d["tiempo_promedio_resolucion_dias"] == 0.0
        assert d["valor_en_riesgo"] == 0

    def test_clasifica_por_dias_restantes(self, client, db_session):
        # Vencida (dias_restantes negativo, abierta)
        _seed(db_session, dias_restantes=-3, valor_objetado=10_000,
              estado="RADICADA")
        # Crítica (entre 0 y 3, abierta)
        _seed(db_session, dias_restantes=2, valor_objetado=20_000,
              estado="RADICADA")
        # En tiempo (>3 días, abierta)
        _seed(db_session, dias_restantes=10, valor_objetado=30_000,
              estado="RADICADA")

        r = client.get("/glosas/stats/cumplimiento-sla")
        d = r.json()
        assert d["total"] == 3
        assert d["vencidas"] == 1
        assert d["criticas"] == 1
        assert d["en_tiempo"] == 1
        assert d["cerradas"] == 0
        # valor_en_riesgo = vencidas + críticas
        assert d["valor_en_riesgo"] == 30_000

    def test_cerradas_no_cuentan_como_vencidas(self, client, db_session):
        # Estado cerrado pero dias_restantes negativo → no cuenta como vencida
        _seed(db_session, dias_restantes=-100, estado="ACEPTADA",
              valor_objetado=999)
        r = client.get("/glosas/stats/cumplimiento-sla")
        d = r.json()
        assert d["vencidas"] == 0
        assert d["cerradas"] == 1
        assert d["valor_en_riesgo"] == 0

    def test_tasa_cumplimiento(self, client, db_session):
        ahora = ahora_utc()
        # Cerrada a tiempo (decisión antes del vencimiento)
        _seed(db_session, estado="LEVANTADA",
              fecha_vencimiento=ahora + timedelta(days=2),
              fecha_decision_eps=ahora - timedelta(days=1))
        # Cerrada tarde
        _seed(db_session, estado="ACEPTADA",
              fecha_vencimiento=ahora - timedelta(days=5),
              fecha_decision_eps=ahora - timedelta(days=2))

        r = client.get("/glosas/stats/cumplimiento-sla")
        d = r.json()
        assert d["cerradas"] == 2
        assert d["cerradas_a_tiempo"] == 1
        assert d["tasa_cumplimiento_pct"] == 50.0

    def test_tiempo_promedio_resolucion(self, client, db_session):
        ahora = ahora_utc()
        _seed(db_session, estado="ACEPTADA",
              creado_en=ahora - timedelta(days=10),
              fecha_decision_eps=ahora)
        _seed(db_session, estado="ACEPTADA",
              creado_en=ahora - timedelta(days=20),
              fecha_decision_eps=ahora)
        r = client.get("/glosas/stats/cumplimiento-sla")
        d = r.json()
        # promedio (10+20)/2 = 15 días
        assert 14.9 < d["tiempo_promedio_resolucion_dias"] < 15.1
