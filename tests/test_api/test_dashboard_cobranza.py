"""Tests del endpoint GET /glosas/stats/dashboard-cobranza (R300 P1 — hito)."""
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


def _seed(db, eps, factura, saldo, dias_atras=5,
          estado="RADICADA"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
        saldo_factura=saldo,
        valor_factura=10000,
    ))
    db.commit()


class TestDashboardCobranza:
    def test_kpis_y_top(self, client, db_session):
        _seed(db_session, "SANITAS", "F100", 5000, dias_atras=5)
        _seed(db_session, "SANITAS", "F200", 10000, dias_atras=45)
        _seed(db_session, "EPS001", "F300", 3000, dias_atras=120)
        # Cerrada no debe contar
        _seed(
            db_session, "MALA", "F999", 99999,
            estado="LEVANTADA",
        )

        r = client.get("/glosas/stats/dashboard-cobranza")
        d = r.json()
        assert d["kpis"]["count_abiertas"] == 3
        assert d["kpis"]["saldo_total"] == 18000
        # Top EPS
        eps_top = {it["eps"]: it["saldo"] for it in d["top_eps"]}
        assert eps_top["SANITAS"] == 15000
        # Top facturas
        f_top = {it["factura"]: it["saldo"] for it in d["top_facturas"]}
        assert f_top["F200"] == 10000

    def test_vacio(self, client):
        r = client.get("/glosas/stats/dashboard-cobranza")
        d = r.json()
        assert d["kpis"]["count_abiertas"] == 0
        assert d["top_eps"] == []
