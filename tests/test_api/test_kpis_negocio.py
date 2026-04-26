"""Tests del endpoint GET /sistema/kpis-negocio (R151 P1)."""
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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestKpisNegocio:
    def test_estructura(self, client):
        r = client.get("/sistema/kpis-negocio")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("tasa_levantamiento_global_pct",
                    "tasa_recuperacion_global_pct",
                    "valor_recuperado_acumulado",
                    "valor_pendiente_actual",
                    "tiempo_promedio_resolucion_dias",
                    "glosas_cerradas_30d",
                    "tasa_cumplimiento_sla_30d_pct",
                    "eps_top_recuperacion",
                    "calculado_en"):
            assert key in d

    def test_tasa_levantamiento(self, client, db_session):
        # 2 LEVANTADA + 2 ACEPTADA = 50% tasa_lev
        _seed(db_session, estado="LEVANTADA")
        _seed(db_session, estado="LEVANTADA")
        _seed(db_session, estado="ACEPTADA")
        _seed(db_session, estado="ACEPTADA")

        r = client.get("/sistema/kpis-negocio")
        d = r.json()
        assert d["tasa_levantamiento_global_pct"] == 50.0

    def test_valor_pendiente(self, client, db_session):
        _seed(db_session, estado="RADICADA", valor_objetado=10_000)
        _seed(db_session, estado="LEVANTADA", valor_objetado=5_000)  # cerrada
        r = client.get("/sistema/kpis-negocio")
        d = r.json()
        # Solo la abierta cuenta como pendiente
        assert d["valor_pendiente_actual"] == 10_000

    def test_eps_top_recuperacion(self, client, db_session):
        _seed(db_session, eps="SANITAS", estado="LEVANTADA",
              valor_recuperado=10_000)
        _seed(db_session, eps="OTRA", estado="LEVANTADA",
              valor_recuperado=1_000)
        r = client.get("/sistema/kpis-negocio")
        d = r.json()
        assert d["eps_top_recuperacion"] == "SANITAS"

    def test_glosas_cerradas_30d(self, client, db_session):
        _seed(db_session, estado="LEVANTADA",
              fecha_decision_eps=ahora_utc() - timedelta(days=10))
        _seed(db_session, estado="LEVANTADA",
              fecha_decision_eps=ahora_utc() - timedelta(days=60))  # fuera
        r = client.get("/sistema/kpis-negocio")
        d = r.json()
        assert d["glosas_cerradas_30d"] == 1
