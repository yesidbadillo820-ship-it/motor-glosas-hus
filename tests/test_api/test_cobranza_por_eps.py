"""Tests del endpoint GET /glosas/stats/cobranza-por-eps (R122 P2)."""
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


def _seed(db, eps, valor, estado="RADICADA", valor_rec=0, dias_atras=10):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestCobranzaPorEPS:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cobranza-por-eps")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["valor_pendiente_global"] == 0

    def test_orden_por_valor_pendiente_desc(self, client, db_session):
        # SANITAS: $30k pendiente
        _seed(db_session, "SANITAS", 10_000)
        _seed(db_session, "SANITAS", 20_000)
        # NUEVA EPS: $5k pendiente
        _seed(db_session, "NUEVA EPS", 5_000)

        r = client.get("/glosas/stats/cobranza-por-eps")
        d = r.json()
        assert d["items"][0]["eps"] == "SANITAS"
        assert d["items"][0]["valor_pendiente"] == 30_000
        assert d["items"][1]["eps"] == "NUEVA EPS"

    def test_excluye_eps_sin_pendientes(self, client, db_session):
        # EPS solo con cerradas → no aparece
        _seed(db_session, "TODO_CERRADO", 1000, estado="LEVANTADA",
              valor_rec=1000)
        r = client.get("/glosas/stats/cobranza-por-eps")
        d = r.json()
        assert d["items"] == []

    def test_tasa_historica_por_eps(self, client, db_session):
        # SANITAS histórica: 50% recuperación
        _seed(db_session, "SANITAS", 10_000, estado="LEVANTADA",
              valor_rec=10_000)
        _seed(db_session, "SANITAS", 10_000, estado="ACEPTADA",
              valor_rec=0)
        # SANITAS pendientes: $4k → recuperable estimado $2k
        _seed(db_session, "SANITAS", 4000)

        r = client.get("/glosas/stats/cobranza-por-eps")
        d = r.json()
        item = d["items"][0]
        assert item["tasa_historica_recuperacion_pct"] == 50.0
        assert item["valor_recuperable_estimado"] == 2000

    def test_antiguedad_promedio(self, client, db_session):
        _seed(db_session, "X", 1000, dias_atras=10)
        _seed(db_session, "X", 1000, dias_atras=30)
        r = client.get("/glosas/stats/cobranza-por-eps")
        d = r.json()
        # Promedio = 20 días
        assert d["items"][0]["antiguedad_promedio_dias"] == 20.0

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed(db_session, f"EPS_{i}", 1000)
        r = client.get("/glosas/stats/cobranza-por-eps?top=3")
        d = r.json()
        assert len(d["items"]) == 3
        assert d["total_eps_con_pendientes"] == 10
