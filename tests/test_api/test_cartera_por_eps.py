"""Tests del endpoint GET /glosas/stats/cartera-por-eps (R262 P1)."""
from __future__ import annotations

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


def _seed(db, eps, saldo, valor, estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        saldo_factura=saldo,
        valor_factura=valor,
    ))
    db.commit()


class TestCarteraPorEPS:
    def test_orden_desc(self, client, db_session):
        _seed(db_session, "SANITAS", saldo=10_000, valor=20_000)
        _seed(db_session, "EPS001", saldo=50_000, valor=80_000)
        _seed(db_session, "NUEVA", saldo=5_000, valor=10_000)

        r = client.get("/glosas/stats/cartera-por-eps")
        d = r.json()
        saldos = [it["saldo_total"] for it in d["items"]]
        assert saldos == sorted(saldos, reverse=True)
        assert d["items"][0]["eps"] == "EPS001"
        assert d["items"][0]["pct_saldo"] == 62.5  # 50/80

    def test_pct_global(self, client, db_session):
        _seed(db_session, "X", saldo=300, valor=1000)
        r = client.get("/glosas/stats/cartera-por-eps")
        d = r.json()
        assert d["saldo_total"] == 300
        assert d["valor_factura_total"] == 1000
        assert d["pct_saldo_global"] == 30.0

    def test_solo_abiertas(self, client, db_session):
        _seed(db_session, "ABIERTA", saldo=100, valor=200)
        _seed(db_session, "CERRADA", saldo=999, valor=999, estado="LEVANTADA")
        # Por defecto solo abiertas
        r = client.get("/glosas/stats/cartera-por-eps")
        d = r.json()
        eps_set = {it["eps"] for it in d["items"]}
        assert eps_set == {"ABIERTA"}
        # Con solo_abiertas=false, ambas
        r2 = client.get("/glosas/stats/cartera-por-eps?solo_abiertas=false")
        d2 = r2.json()
        eps_set2 = {it["eps"] for it in d2["items"]}
        assert eps_set2 == {"ABIERTA", "CERRADA"}
