"""Tests del endpoint GET /glosas/stats/eps-tendencia-mensual (R273 P1)."""
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


def _seed(db, eps, estado="LEVANTADA", valor=1000, recuperado=0):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSTendenciaMensual:
    def test_filtra_por_eps(self, client, db_session):
        _seed(db_session, "SANITAS")
        _seed(db_session, "OTRA")
        r = client.get(
            "/glosas/stats/eps-tendencia-mensual?eps=SANITAS"
        )
        d = r.json()
        assert d["eps"] == "SANITAS"
        # Una sola entrada de mes
        assert len(d["serie"]) == 1
        assert d["serie"][0]["creadas"] == 1

    def test_tasa_levantamiento(self, client, db_session):
        _seed(db_session, "XX", estado="LEVANTADA")
        _seed(db_session, "XX", estado="RATIFICADA")
        # 1/2 = 50%
        r = client.get("/glosas/stats/eps-tendencia-mensual?eps=XX")
        d = r.json()
        assert d["serie"][0]["decididas"] == 2
        assert d["serie"][0]["levantadas"] == 1
        assert d["serie"][0]["tasa_levantamiento_pct"] == 50.0

    def test_sin_match(self, client):
        r = client.get(
            "/glosas/stats/eps-tendencia-mensual?eps=NOEXISTE"
        )
        d = r.json()
        assert d["serie"] == []
