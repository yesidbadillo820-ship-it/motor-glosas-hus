"""Tests del endpoint GET /glosas/stats/estatus-eps (R137 P2)."""
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


def _seed(db, eps, estado="RADICADA", **kw):
    base = dict(
        paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(eps=eps, estado=estado, **base))
    db.commit()


class TestEstatusEPS:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/estatus-eps")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []
        assert d["por_status"] == {"VERDE": 0, "AMARILLO": 0, "ROJO": 0}

    def test_eps_verde(self, client, db_session):
        # 5 LEVANTADA + 0 vencidas = saludable
        for _ in range(5):
            _seed(db_session, "BUENA", "LEVANTADA")
        r = client.get("/glosas/stats/estatus-eps")
        d = r.json()
        item = next(it for it in d["items"] if it["eps"] == "BUENA")
        assert item["status"] == "VERDE"

    def test_eps_roja_por_vencidas(self, client, db_session):
        # 16 vencidas → ROJO
        for _ in range(16):
            _seed(db_session, "MALA", "RADICADA", dias_restantes=-5)
        r = client.get("/glosas/stats/estatus-eps")
        d = r.json()
        item = next(it for it in d["items"] if it["eps"] == "MALA")
        assert item["status"] == "ROJO"

    def test_eps_roja_por_tasa_lev_baja(self, client, db_session):
        # 1 LEVANTADA + 5 ACEPTADA → tasa = 16.67% con 6 decididas → ROJO
        _seed(db_session, "PESIMA", "LEVANTADA")
        for _ in range(5):
            _seed(db_session, "PESIMA", "ACEPTADA")
        r = client.get("/glosas/stats/estatus-eps")
        d = r.json()
        item = next(it for it in d["items"] if it["eps"] == "PESIMA")
        assert item["status"] == "ROJO"

    def test_orden_rojo_amarillo_verde(self, client, db_session):
        # Verde
        for _ in range(5):
            _seed(db_session, "VERDE_EPS", "LEVANTADA")
        # Rojo
        for _ in range(16):
            _seed(db_session, "ROJA_EPS", "RADICADA", dias_restantes=-5)
        r = client.get("/glosas/stats/estatus-eps")
        d = r.json()
        # ROJA primero
        assert d["items"][0]["status"] == "ROJO"
