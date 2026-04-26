"""Tests del endpoint /glosas/stats/por-eps (R68 P2)."""
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
    return UsuarioRecord(id=1, email="x@hus.com", rol="AUDITOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, valor_aceptado=0,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestStatsPorEps:
    def test_sin_glosas(self, client):
        r = client.get("/glosas/stats/por-eps")
        assert r.status_code == 200
        d = r.json()
        assert d["total_eps"] == 0

    def test_agregaciones_correctas(self, client, db_session):
        # FAMISANAR: 2 glosas, $300k objetado, $50k aceptado → recup $250k
        _seed(db_session, eps="FAMISANAR", valor_objetado=200_000, valor_aceptado=0)
        _seed(db_session, eps="FAMISANAR", valor_objetado=100_000, valor_aceptado=50_000)
        # SALUD TOTAL: 1, $80k objetado, $0 → recup $80k
        _seed(db_session, eps="SALUD TOTAL", valor_objetado=80_000, valor_aceptado=0)
        r = client.get("/glosas/stats/por-eps")
        d = r.json()
        assert d["total_eps"] == 2
        # Buscar FAMISANAR
        fami = next(x for x in d["items"] if x["eps"] == "FAMISANAR")
        assert fami["count"] == 2
        assert fami["valor_objetado"] == 300_000
        assert fami["valor_aceptado"] == 50_000
        assert fami["valor_recuperado"] == 250_000
        # tasa = 250/300 = 83.3
        assert abs(fami["tasa_exito_pct"] - 83.3) < 0.5

    def test_orden_por_valor_objetado_desc(self, client, db_session):
        _seed(db_session, eps="A", valor_objetado=100_000)
        _seed(db_session, eps="B", valor_objetado=500_000)
        _seed(db_session, eps="C", valor_objetado=200_000)
        r = client.get("/glosas/stats/por-eps")
        d = r.json()
        eps_ordenadas = [x["eps"] for x in d["items"]]
        assert eps_ordenadas == ["B", "C", "A"]

    def test_filtro_isnotnone_no_explota(self, client, db_session):
        """El filtro .isnot(None) en el endpoint debe trabajar OK con
        EPSs reales (NOT NULL constraint impide eps=None en BD)."""
        _seed(db_session, eps="FAMISANAR")
        _seed(db_session, eps="SALUD TOTAL")
        r = client.get("/glosas/stats/por-eps")
        assert r.status_code == 200
        d = r.json()
        assert d["total_eps"] == 2

    def test_filtro_ventana(self, client, db_session):
        _seed(db_session, eps="VIEJA",
              creado_en=ahora_utc() - timedelta(days=200))
        _seed(db_session, eps="NUEVA",
              creado_en=ahora_utc() - timedelta(days=10))
        r = client.get("/glosas/stats/por-eps?dias=90")
        d = r.json()
        eps_lista = [x["eps"] for x in d["items"]]
        assert "NUEVA" in eps_lista
        assert "VIEJA" not in eps_lista

    def test_tasa_exito_zero_div_safe(self, client, db_session):
        """Si valor_objetado=0 (rare), tasa_exito debe ser 0, no NaN/error."""
        _seed(db_session, eps="X", valor_objetado=0, valor_aceptado=0)
        r = client.get("/glosas/stats/por-eps")
        d = r.json()
        assert d["items"][0]["tasa_exito_pct"] == 0
