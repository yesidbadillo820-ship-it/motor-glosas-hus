"""Tests del endpoint GET /analytics/win-rate-detalle (feature #7)."""

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


def _seed(
    db,
    *,
    eps,
    codigo,
    estado,
    dias_atras,
    valor_objetado=100_000,
    valor_recuperado=0.0,
):
    db.add(
        GlosaRecord(
            eps=eps,
            paciente="P",
            codigo_glosa=codigo,
            valor_objetado=valor_objetado,
            valor_recuperado=valor_recuperado,
            etapa="X",
            estado=estado,
            creado_en=ahora_utc(),
            fecha_decision_eps=ahora_utc() - timedelta(days=dias_atras),
        )
    )
    db.commit()


class TestWinRateDetalle:
    def test_agrupa_por_eps_y_codigo(self, client, db_session):
        # (FAMISANAR, TA0201): 3 levantadas / 1 ratificada → 75%
        for _ in range(3):
            _seed(
                db_session,
                eps="FAMISANAR",
                codigo="TA0201",
                estado="LEVANTADA",
                dias_atras=10,
                valor_recuperado=100_000,
            )
        _seed(db_session, eps="FAMISANAR", codigo="TA0201", estado="RATIFICADA", dias_atras=10)
        # (COMPENSAR, SO0501): 1 levantada / 1 ratificada → 50%
        _seed(
            db_session,
            eps="COMPENSAR",
            codigo="SO0501",
            estado="LEVANTADA",
            dias_atras=5,
            valor_recuperado=50_000,
        )
        _seed(db_session, eps="COMPENSAR", codigo="SO0501", estado="RATIFICADA", dias_atras=5)

        r = client.get("/analytics/win-rate-detalle?dias=30")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_combinaciones"] == 2

        # Ordenado por valor_recuperado desc → FAMISANAR/TA0201 primero
        fam = d["items"][0]
        assert fam["eps"] == "FAMISANAR"
        assert fam["codigo"] == "TA0201"
        assert fam["n_total"] == 4
        assert fam["n_levantadas"] == 3
        assert fam["n_ratificadas"] == 1
        assert fam["tasa_levantamiento_pct"] == 75.0
        assert fam["valor_recuperado_total"] == 300_000

        comp = d["items"][1]
        assert comp["eps"] == "COMPENSAR"
        assert comp["tasa_levantamiento_pct"] == 50.0

    def test_tendencia_compara_con_periodo_anterior(self, client, db_session):
        # Periodo actual (últimos 30d): 4 levantadas / 1 ratificada → 80%
        for _ in range(4):
            _seed(
                db_session,
                eps="FAM",
                codigo="TA0201",
                estado="LEVANTADA",
                dias_atras=10,
            )
        _seed(db_session, eps="FAM", codigo="TA0201", estado="RATIFICADA", dias_atras=10)
        # Periodo anterior (días 31-60): 1 levantada / 3 ratificadas → 25%
        _seed(db_session, eps="FAM", codigo="TA0201", estado="LEVANTADA", dias_atras=40)
        for _ in range(3):
            _seed(
                db_session,
                eps="FAM",
                codigo="TA0201",
                estado="RATIFICADA",
                dias_atras=40,
            )

        r = client.get("/analytics/win-rate-detalle?dias=30")
        item = r.json()["items"][0]
        assert item["tasa_levantamiento_pct"] == 80.0
        # Tendencia: 80 - 25 = +55 puntos
        assert item["tendencia_3m_pct"] == 55.0

    def test_filtro_por_eps(self, client, db_session):
        _seed(db_session, eps="FAM", codigo="TA0201", estado="LEVANTADA", dias_atras=10)
        _seed(db_session, eps="COMPENSAR", codigo="TA0201", estado="LEVANTADA", dias_atras=10)
        r = client.get("/analytics/win-rate-detalle?dias=30&eps=FAM")
        d = r.json()
        assert d["total_combinaciones"] == 1
        assert d["items"][0]["eps"] == "FAM"

    def test_ventana_excluye_decisiones_viejas(self, client, db_session):
        # 1 decisión hace 200 días → fuera de ventana de 30
        _seed(db_session, eps="FAM", codigo="TA0201", estado="LEVANTADA", dias_atras=200)
        r = client.get("/analytics/win-rate-detalle?dias=30")
        assert r.json()["total_combinaciones"] == 0

    def test_dias_acotado_a_rango_valido(self, client):
        # dias=1 se sube a min=7, dias=99999 se baja a max=365
        r = client.get("/analytics/win-rate-detalle?dias=1")
        assert r.json()["ventana_dias"] == 7
        r = client.get("/analytics/win-rate-detalle?dias=99999")
        assert r.json()["ventana_dias"] == 365
