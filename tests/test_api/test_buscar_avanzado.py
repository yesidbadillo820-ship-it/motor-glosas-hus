"""Tests del endpoint GET /glosas/buscar-avanzado (R94 P1)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="TA0201",
        factura="F-001", valor_objetado=1000, etapa="X",
        estado="RADICADA", creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestBuscarAvanzado:
    def test_sin_filtros_devuelve_todo(self, client, db_session):
        for _ in range(3):
            _seed(db_session)
        r = client.get("/glosas/buscar-avanzado")
        d = r.json()
        assert d["total_coincidencias"] == 3
        assert len(d["items"]) == 3

    def test_filtro_eps_partial(self, client, db_session):
        _seed(db_session, eps="SANITAS")
        _seed(db_session, eps="NUEVA SANITAS")  # contiene "SANITAS"
        _seed(db_session, eps="NUEVA EPS")
        r = client.get("/glosas/buscar-avanzado?eps=SANITAS")
        d = r.json()
        assert d["total_coincidencias"] == 2

    def test_filtro_paciente_case_insensitive(self, client, db_session):
        _seed(db_session, paciente="Pedro Pérez")
        r = client.get("/glosas/buscar-avanzado?paciente=pedro")
        assert r.json()["total_coincidencias"] == 1

    def test_combinacion_AND(self, client, db_session):
        _seed(db_session, eps="SANITAS", estado="LEVANTADA",
              valor_objetado=5000)
        _seed(db_session, eps="SANITAS", estado="ACEPTADA",
              valor_objetado=5000)
        _seed(db_session, eps="NUEVA EPS", estado="LEVANTADA",
              valor_objetado=5000)
        r = client.get(
            "/glosas/buscar-avanzado?eps=SANITAS&estado=LEVANTADA"
        )
        d = r.json()
        assert d["total_coincidencias"] == 1

    def test_filtro_valor_rango(self, client, db_session):
        _seed(db_session, valor_objetado=500)
        _seed(db_session, valor_objetado=5000)
        _seed(db_session, valor_objetado=50000)
        r = client.get(
            "/glosas/buscar-avanzado?valor_min=1000&valor_max=10000"
        )
        d = r.json()
        assert d["total_coincidencias"] == 1
        assert d["items"][0]["valor_objetado"] == 5000.0

    def test_filtro_fecha_invalida_400(self, client):
        r = client.get("/glosas/buscar-avanzado?fecha_desde=ayer")
        assert r.status_code == 400

    def test_limit_respetado(self, client, db_session):
        for _ in range(15):
            _seed(db_session)
        r = client.get("/glosas/buscar-avanzado?limit=5")
        d = r.json()
        assert d["total_coincidencias"] == 15  # total real
        assert len(d["items"]) == 5             # limitado
