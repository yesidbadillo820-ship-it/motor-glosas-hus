"""Tests del endpoint GET /glosas/{id}/dictamen-similar-anterior (R231 P1)."""
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


def _seed(db, gid, eps="SANITAS", codigo="TA0201",
          estado="RADICADA", dictamen=None, valor_rec=0):
    db.add(GlosaRecord(
        id=gid, eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
        fecha_decision_eps=ahora_utc(),
        dictamen=dictamen,
    ))
    db.commit()


class TestDictamenSimilarAnterior:
    def test_404(self, client):
        r = client.get("/glosas/99999/dictamen-similar-anterior")
        assert r.status_code == 404

    def test_sin_match(self, client, db_session):
        _seed(db_session, 1)
        r = client.get("/glosas/1/dictamen-similar-anterior")
        d = r.json()
        assert d["sin_match"] is True

    def test_match_levantada(self, client, db_session):
        _seed(db_session, 1)  # target
        _seed(db_session, 2,
              estado="LEVANTADA",
              dictamen="dictamen ganador",
              valor_rec=10000)

        r = client.get("/glosas/1/dictamen-similar-anterior")
        d = r.json()
        assert d["sin_match"] is False
        assert d["glosa_id_origen"] == 2
        assert "ganador" in d["dictamen"]
        assert d["valor_recuperado_origen"] == 10000

    def test_aislamiento_eps_codigo(self, client, db_session):
        _seed(db_session, 1, eps="SANITAS", codigo="TA0201")
        # Otra EPS, mismo código
        _seed(db_session, 2, eps="OTRA", codigo="TA0201",
              estado="LEVANTADA", dictamen="x")
        # Misma EPS, otro código
        _seed(db_session, 3, eps="SANITAS", codigo="FA0603",
              estado="LEVANTADA", dictamen="y")

        r = client.get("/glosas/1/dictamen-similar-anterior")
        d = r.json()
        # No debe matchear ninguna
        assert d["sin_match"] is True
