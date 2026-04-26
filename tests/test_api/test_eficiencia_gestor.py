"""Tests del endpoint GET /glosas/stats/eficiencia-gestor (R98 P1)."""
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


def _seed(db, gestor, estado, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        gestor_nombre=gestor,
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestEficienciaGestor:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/eficiencia-gestor?min_glosas=1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_gestores_evaluados"] == 0
        assert d["items"] == []

    def test_solo_cerradas(self, client, db_session):
        # Solo glosas cerradas cuentan
        _seed(db_session, "Alice", "RADICADA")  # no
        _seed(db_session, "Alice", "LEVANTADA")  # sí
        r = client.get("/glosas/stats/eficiencia-gestor?min_glosas=1")
        d = r.json()
        # Alice tiene 1 cerrada
        assert d["items"][0]["total_cerradas"] == 1

    def test_ranking_por_tasa_levantamiento(self, client, db_session):
        # Alice: 4/5 = 80%
        for _ in range(4):
            _seed(db_session, "Alice", "LEVANTADA")
        _seed(db_session, "Alice", "ACEPTADA")
        # Bob: 2/5 = 40%
        for _ in range(2):
            _seed(db_session, "Bob", "LEVANTADA")
        for _ in range(3):
            _seed(db_session, "Bob", "ACEPTADA")

        r = client.get("/glosas/stats/eficiencia-gestor?min_glosas=1")
        d = r.json()
        assert d["items"][0]["gestor"] == "Alice"
        assert d["items"][0]["tasa_levantamiento_pct"] == 80.0
        assert d["items"][1]["gestor"] == "Bob"
        assert d["items"][1]["tasa_levantamiento_pct"] == 40.0

    def test_filtra_min_glosas(self, client, db_session):
        # Alice: 5 cerradas → entra con min=3
        for _ in range(5):
            _seed(db_session, "Alice", "LEVANTADA")
        # Pequeña: 2 → no entra con min=3
        for _ in range(2):
            _seed(db_session, "Pequeña", "LEVANTADA")
        r = client.get("/glosas/stats/eficiencia-gestor?min_glosas=3")
        d = r.json()
        gestores = [it["gestor"] for it in d["items"]]
        assert "Alice" in gestores
        assert "Pequeña" not in gestores

    def test_tasa_recuperacion(self, client, db_session):
        _seed(db_session, "Alice", "LEVANTADA",
              valor_objetado=10000, valor_recuperado=8000)
        _seed(db_session, "Alice", "LEVANTADA",
              valor_objetado=5000, valor_recuperado=2000)
        r = client.get("/glosas/stats/eficiencia-gestor?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Alice")
        # 10000/15000 = 66.67%
        assert item["tasa_recuperacion_pct"] == 66.67

    def test_tiempo_promedio(self, client, db_session):
        ahora = ahora_utc()
        _seed(db_session, "Alice", "LEVANTADA",
              creado_en=ahora - timedelta(days=10),
              fecha_decision_eps=ahora)
        _seed(db_session, "Alice", "LEVANTADA",
              creado_en=ahora - timedelta(days=20),
              fecha_decision_eps=ahora)
        r = client.get("/glosas/stats/eficiencia-gestor?min_glosas=1")
        d = r.json()
        item = next(it for it in d["items"] if it["gestor"] == "Alice")
        assert 14.9 < item["tiempo_promedio_resolucion_dias"] < 15.1
