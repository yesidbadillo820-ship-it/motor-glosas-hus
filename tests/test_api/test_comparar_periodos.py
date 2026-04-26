"""Tests del endpoint GET /glosas/stats/comparar-periodos (R118 P1)."""
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


def _seed(db, dias_atras_creado, estado="RADICADA",
          dias_atras_dec=None, valor_rec=0):
    fecha_dec = (
        ahora_utc() - timedelta(days=dias_atras_dec)
        if dias_atras_dec is not None else None
    )
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras_creado),
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestCompararPeriodos:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/comparar-periodos")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "periodo_actual", "periodo_previo",
                    "deltas"):
            assert key in d

    def test_glosas_creadas_actual_vs_previo(self, client, db_session):
        # 3 glosas en últimos 30d
        for d in [5, 10, 20]:
            _seed(db_session, dias_atras_creado=d)
        # 2 glosas en 30-60d previo
        for d in [40, 50]:
            _seed(db_session, dias_atras_creado=d)

        r = client.get("/glosas/stats/comparar-periodos?dias=30")
        d = r.json()
        assert d["periodo_actual"]["glosas_creadas"] == 3
        assert d["periodo_previo"]["glosas_creadas"] == 2

    def test_delta_calculado_correctamente(self, client, db_session):
        # Actual: 4 creadas, previo: 2 → +2 absoluto, +100% pct
        for d in [5, 10, 15, 20]:
            _seed(db_session, dias_atras_creado=d)
        for d in [40, 50]:
            _seed(db_session, dias_atras_creado=d)

        r = client.get("/glosas/stats/comparar-periodos?dias=30")
        d = r.json()
        delta = d["deltas"]["glosas_creadas"]
        assert delta["absoluto"] == 2
        assert delta["pct"] == 100.0

    def test_pct_null_si_previo_cero(self, client, db_session):
        # Solo glosas en período actual, ninguna previa
        _seed(db_session, dias_atras_creado=5)
        r = client.get("/glosas/stats/comparar-periodos?dias=30")
        d = r.json()
        # División por cero → pct=null
        assert d["deltas"]["glosas_creadas"]["pct"] is None
        assert d["deltas"]["glosas_creadas"]["absoluto"] == 1

    def test_valor_recuperado_se_acumula(self, client, db_session):
        # Cerrada en actual con $5k recuperado
        _seed(db_session, dias_atras_creado=10, estado="LEVANTADA",
              dias_atras_dec=5, valor_rec=5000)
        r = client.get("/glosas/stats/comparar-periodos?dias=30")
        d = r.json()
        assert d["periodo_actual"]["valor_recuperado"] == 5000
