"""Tests del endpoint GET /glosas/stats/velocidad-equipo (R115 P1)."""
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


def _seed(db, dias_atras_dec=None, estado="LEVANTADA"):
    fecha_dec = (
        ahora_utc() - timedelta(days=dias_atras_dec)
        if dias_atras_dec is not None else None
    )
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=fecha_dec,
    ))
    db.commit()


class TestVelocidadEquipo:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/velocidad-equipo")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["cerradas_ultimos_7d"] == 0
        assert d["cerradas_ultimos_30d"] == 0
        assert d["pendientes_actuales"] == 0

    def test_clasifica_por_ventana(self, client, db_session):
        # Cerradas en distintas ventanas
        _seed(db_session, dias_atras_dec=3)    # ≤7d, ≤30d, ≤90d
        _seed(db_session, dias_atras_dec=20)   # no7, ≤30d, ≤90d
        _seed(db_session, dias_atras_dec=60)   # no7, no30, ≤90d
        _seed(db_session, dias_atras_dec=120)  # nada
        r = client.get("/glosas/stats/velocidad-equipo")
        d = r.json()
        assert d["cerradas_ultimos_7d"] == 1
        assert d["cerradas_ultimos_30d"] == 2
        assert d["cerradas_ultimos_90d"] == 3

    def test_velocidad_diaria(self, client, db_session):
        # 30 cerradas en 30d → velocidad = 1/dia
        for _ in range(30):
            _seed(db_session, dias_atras_dec=15)
        r = client.get("/glosas/stats/velocidad-equipo")
        d = r.json()
        assert d["velocidad_diaria_promedio_30d"] == 1.0

    def test_estimado_dias_cerrar_pendientes(self, client, db_session):
        # 30 cerradas en 30d (vel = 1/d), 10 pendientes → 10 días
        for _ in range(30):
            _seed(db_session, dias_atras_dec=15)
        for _ in range(10):
            _seed(db_session, estado="RADICADA")
        r = client.get("/glosas/stats/velocidad-equipo")
        d = r.json()
        assert d["pendientes_actuales"] == 10
        assert d["dias_estimados_cerrar_pendientes"] == 10.0

    def test_sin_velocidad_estimado_null(self, client, db_session):
        # Pendientes sin cerradas históricas → no se puede estimar
        for _ in range(5):
            _seed(db_session, estado="RADICADA")
        r = client.get("/glosas/stats/velocidad-equipo")
        d = r.json()
        assert d["dias_estimados_cerrar_pendientes"] is None
