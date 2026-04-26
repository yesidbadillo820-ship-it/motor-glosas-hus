"""Tests del endpoint GET /glosas/stats/comparativa-eps (R90 P2)."""
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


def _seed(db, eps, estado, valor=1000, **kw):
    base = dict(
        eps=eps, paciente="X", codigo_glosa="TA0201",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestComparativaEPS:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/comparativa-eps?min_glosas=1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_eps_evaluadas"] == 0
        assert d["items"] == []

    def test_ranking_por_tasa_levantamiento(self, client, db_session):
        # SANITAS: 4 LEVANTADAS de 5 decididas = 80%
        for _ in range(4):
            _seed(db_session, "SANITAS", "LEVANTADA")
        _seed(db_session, "SANITAS", "ACEPTADA")
        # NUEVA EPS: 1 LEVANTADA de 5 decididas = 20%
        _seed(db_session, "NUEVA EPS", "LEVANTADA")
        for _ in range(4):
            _seed(db_session, "NUEVA EPS", "ACEPTADA")

        r = client.get("/glosas/stats/comparativa-eps?min_glosas=1")
        d = r.json()
        # SANITAS debe ir primero (80% > 20%)
        assert d["items"][0]["eps"] == "SANITAS"
        assert d["items"][0]["tasa_levantamiento_pct"] == 80.0
        assert d["items"][1]["eps"] == "NUEVA EPS"
        assert d["items"][1]["tasa_levantamiento_pct"] == 20.0

    def test_filtra_min_glosas(self, client, db_session):
        # SANITAS: 10 → entra
        for _ in range(10):
            _seed(db_session, "SANITAS", "LEVANTADA")
        # PEQUENA: 3 → no entra con min_glosas=5
        for _ in range(3):
            _seed(db_session, "PEQUENA", "LEVANTADA")

        r = client.get("/glosas/stats/comparativa-eps?min_glosas=5")
        d = r.json()
        eps_list = [it["eps"] for it in d["items"]]
        assert "SANITAS" in eps_list
        assert "PEQUENA" not in eps_list

    def test_pendientes_no_cuentan_para_tasa(self, client, db_session):
        # 1 levantada + 9 pendientes (RADICADA) → tasa 100% (1/1)
        _seed(db_session, "X", "LEVANTADA")
        for _ in range(9):
            _seed(db_session, "X", "RADICADA")
        r = client.get("/glosas/stats/comparativa-eps?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["eps"] == "X")
        assert item["total_glosas"] == 10
        assert item["pendientes"] == 9
        assert item["levantadas"] == 1
        assert item["tasa_levantamiento_pct"] == 100.0

    def test_valores_acumulados(self, client, db_session):
        _seed(db_session, "X", "LEVANTADA",
              valor=10_000, valor_recuperado=10_000)
        _seed(db_session, "X", "ACEPTADA",
              valor=5_000, valor_recuperado=0)
        r = client.get("/glosas/stats/comparativa-eps?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["eps"] == "X")
        assert item["valor_objetado_total"] == 15_000
        assert item["valor_recuperado_total"] == 10_000

    def test_tiempo_promedio_decision(self, client, db_session):
        ahora = ahora_utc()
        _seed(db_session, "X", "LEVANTADA",
              creado_en=ahora - timedelta(days=10),
              fecha_decision_eps=ahora)
        _seed(db_session, "X", "LEVANTADA",
              creado_en=ahora - timedelta(days=20),
              fecha_decision_eps=ahora)
        r = client.get("/glosas/stats/comparativa-eps?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["eps"] == "X")
        assert 14.9 < item["tiempo_promedio_decision_dias"] < 15.1
