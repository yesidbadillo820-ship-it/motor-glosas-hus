"""Tests del endpoint GET /glosas/stats/cohorte-mensual (R103 P1)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def _seed(db, creado, estado="RADICADA", dias_resolucion=None):
    fecha_dec = None
    if dias_resolucion is not None and estado in {
        "ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA",
    }:
        fecha_dec = creado + timedelta(days=dias_resolucion)
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=creado,
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestCohorteMensual:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/cohorte-mensual")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["serie"] == []

    def test_agrupa_por_mes_creacion(self, client, db_session):
        # 2 glosas en 2026-04
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 4, 15, tzinfo=timezone.utc))
        # 1 glosa en 2026-03
        _seed(db_session, datetime(2026, 3, 1, tzinfo=timezone.utc))

        r = client.get("/glosas/stats/cohorte-mensual?meses=24")
        d = r.json()
        cohortes = {s["cohorte"]: s for s in d["serie"]}
        assert "2026-04" in cohortes
        assert cohortes["2026-04"]["total_glosas"] == 2
        assert cohortes["2026-03"]["total_glosas"] == 1

    def test_metricas_cierre_30_60_90(self, client, db_session):
        # 4 glosas en abril:
        # - 1 cerrada en 10 días (≤30, ≤60, ≤90)
        # - 1 cerrada en 50 días (no ≤30, ≤60, ≤90)
        # - 1 cerrada en 100 días (no ≤30, no ≤60, no ≤90)
        # - 1 abierta
        creado = datetime(2026, 4, 1, tzinfo=timezone.utc)
        _seed(db_session, creado, "LEVANTADA", dias_resolucion=10)
        _seed(db_session, creado, "LEVANTADA", dias_resolucion=50)
        _seed(db_session, creado, "LEVANTADA", dias_resolucion=100)
        _seed(db_session, creado, "RADICADA")

        r = client.get("/glosas/stats/cohorte-mensual?meses=24")
        d = r.json()
        item = next(s for s in d["serie"] if s["cohorte"] == "2026-04")
        # 1/4 cerradas dentro de 30d (la de 10d) = 25%
        assert item["cierre_30d_pct"] == 25.0
        # 2/4 cerradas dentro de 60d (10d, 50d) = 50%
        assert item["cierre_60d_pct"] == 50.0
        # 2/4 cerradas dentro de 90d (10d, 50d) = 50%
        # (la de 100d ya excede; la abierta nunca cuenta)
        assert item["cierre_90d_pct"] == 50.0

    def test_serie_ordenada_ascendente(self, client, db_session):
        _seed(db_session, datetime(2026, 4, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _seed(db_session, datetime(2026, 3, 1, tzinfo=timezone.utc))
        r = client.get("/glosas/stats/cohorte-mensual?meses=24")
        d = r.json()
        cohortes = [s["cohorte"] for s in d["serie"]]
        assert cohortes == sorted(cohortes)
