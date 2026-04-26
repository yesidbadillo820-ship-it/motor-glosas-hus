"""Tests del endpoint GET /contratos/ranking (R100 P2)."""
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


def _seed(db, eps, valor_obj=1000, valor_rec=500):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor_obj, valor_recuperado=valor_rec,
        etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestContratosRanking:
    def test_vacio(self, client):
        r = client.get("/contratos/ranking?min_glosas=1")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_contratos_evaluados"] == 0
        assert d["items"] == []

    def test_orden_por_valor_recuperado_desc(self, client, db_session):
        # SANITAS: 30k recuperado
        for _ in range(3):
            _seed(db_session, "SANITAS", valor_rec=10_000)
        # NUEVA EPS: 6k recuperado
        for _ in range(3):
            _seed(db_session, "NUEVA EPS", valor_rec=2_000)

        r = client.get("/contratos/ranking?min_glosas=1")
        d = r.json()
        assert d["items"][0]["eps"] == "SANITAS"
        assert d["items"][0]["valor_recuperado_total"] == 30_000
        assert d["items"][0]["ranking_position"] == 1
        assert d["items"][1]["eps"] == "NUEVA EPS"
        assert d["items"][1]["ranking_position"] == 2

    def test_filtra_min_glosas(self, client, db_session):
        for _ in range(10):
            _seed(db_session, "GRANDE")
        for _ in range(2):
            _seed(db_session, "PEQUENA")
        r = client.get("/contratos/ranking?min_glosas=5")
        d = r.json()
        eps_list = [it["eps"] for it in d["items"]]
        assert "GRANDE" in eps_list
        assert "PEQUENA" not in eps_list

    def test_tasa_recuperacion(self, client, db_session):
        _seed(db_session, "X", valor_obj=10_000, valor_rec=8_000)
        r = client.get("/contratos/ranking?min_glosas=1")
        d = r.json()
        assert d["items"][0]["tasa_recuperacion_pct"] == 80.0
