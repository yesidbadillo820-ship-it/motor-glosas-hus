"""Ronda 30 — regresiones de estadísticas / números de cartera.

#11 dashboard-cobranza: saldo_factura (campo a nivel de factura) se sumaba
    una vez por glosa → doble conteo de la cartera.
#12/#19 glosas RATIFICADAS caían como 'abiertas'/'vencidas' y no como
    decididas (rama muerta).
#20 stats_concentracion_pareto: ZeroDivisionError con objetado total 0.
"""

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
def client(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    usuario = UsuarioRecord(id=1, email="a@hus.com", rol="SUPER_ADMIN", activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _g(db, **kw):
    kw.setdefault("estado", "PENDIENTE")
    kw.setdefault("creado_en", ahora_utc())
    db.add(GlosaRecord(**kw))
    db.commit()


# ── #11 no doble conteo de saldo_factura ─────────────────────────────────


class TestDashboardCobranzaSinDobleConteo:
    def test_saldo_por_factura_se_cuenta_una_vez(self, client, db_session):
        # 3 glosas de la MISMA factura, cada una con el saldo de la factura.
        for cod in ("TA0801", "SO0101", "FA0101"):
            _g(
                db_session,
                eps="FAMISANAR",
                factura="HUS900",
                codigo_glosa=cod,
                estado="PENDIENTE",
                saldo_factura=1_000_000,
                valor_factura=1_000_000,
            )
        r = client.get("/glosas/stats/dashboard-cobranza")
        assert r.status_code == 200
        kpis = r.json()["kpis"]
        # el saldo de la factura se cuenta UNA vez, no 3
        assert kpis["saldo_total"] == 1_000_000
        assert kpis["valor_factura_total"] == 1_000_000


# ── #20 pareto sin ZeroDivision ──────────────────────────────────────────


class TestParetoSinCrash:
    def test_objetado_total_cero_no_revienta(self, client, db_session):
        _g(db_session, eps="X", valor_objetado=0)
        r = client.get("/glosas/stats/concentracion-pareto")
        assert r.status_code == 200
        assert r.json()["valor_total"] == 0
