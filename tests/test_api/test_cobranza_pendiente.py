"""Tests del endpoint GET /glosas/stats/cobranza-pendiente (R120 P2)."""
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


def _seed(db, dias_atras=10, valor=1000, estado="RADICADA",
          valor_rec=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestCobranzaPendiente:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cobranza-pendiente")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_pendientes"] == 0
        assert d["valor_pendiente_total"] == 0
        # Aunque vacío, los 4 buckets están presentes en 0
        assert len(d["buckets"]) == 4

    def test_clasifica_por_antiguedad(self, client, db_session):
        _seed(db_session, dias_atras=5, valor=1000)    # <30d
        _seed(db_session, dias_atras=45, valor=2000)   # 30-60d
        _seed(db_session, dias_atras=70, valor=3000)   # 60-90d
        _seed(db_session, dias_atras=120, valor=4000)  # >90d

        r = client.get("/glosas/stats/cobranza-pendiente")
        d = r.json()
        buckets = {b["rango_antiguedad"]: b for b in d["buckets"]}
        assert buckets["<30d"]["count"] == 1
        assert buckets["30-60d"]["count"] == 1
        assert buckets["60-90d"]["count"] == 1
        assert buckets[">90d"]["count"] == 1

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, estado="LEVANTADA", valor=99999)
        _seed(db_session, estado="ACEPTADA", valor=99999)
        r = client.get("/glosas/stats/cobranza-pendiente")
        d = r.json()
        assert d["total_pendientes"] == 0

    def test_tasa_historica_extrapolada(self, client, db_session):
        # Cerradas: $10k recuperado / $20k objetado → tasa 50%
        _seed(db_session, estado="LEVANTADA", valor=10000, valor_rec=10000)
        _seed(db_session, estado="ACEPTADA", valor=10000, valor_rec=0)
        # Pendientes: $4k → recuperable estimado $2k
        _seed(db_session, dias_atras=5, valor=4000, estado="RADICADA")

        r = client.get("/glosas/stats/cobranza-pendiente")
        d = r.json()
        assert d["tasa_historica_recuperacion_pct"] == 50.0
        assert d["valor_pendiente_total"] == 4000
        assert d["valor_recuperable_estimado_total"] == 2000

    def test_pct_count_y_valor(self, client, db_session):
        # 4 glosas en <30d ($1k cada) + 1 en >90d ($96k)
        for _ in range(4):
            _seed(db_session, dias_atras=5, valor=1000)
        _seed(db_session, dias_atras=120, valor=96000)

        r = client.get("/glosas/stats/cobranza-pendiente")
        d = r.json()
        buckets = {b["rango_antiguedad"]: b for b in d["buckets"]}
        # <30d: 4/5 = 80% del count, pero solo 4k/100k = 4% del valor
        assert buckets["<30d"]["pct_count"] == 80.0
        assert buckets["<30d"]["pct_valor"] == 4.0
        # >90d: 1/5 = 20% del count, 96% del valor
        assert buckets[">90d"]["pct_count"] == 20.0
        assert buckets[">90d"]["pct_valor"] == 96.0
