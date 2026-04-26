"""Tests del endpoint GET /glosas/stats/criticas-economicas (R201 P1)."""
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


def _seed(db, valor, dr, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dias_restantes=dr,
    ))
    db.commit()


class TestCriticasEconomicas:
    def test_orden_score_desc(self, client, db_session):
        # Glosa 1: $10M con 0d → score muy alto
        _seed(db_session, valor=10_000_000, dr=0)
        # Glosa 2: $1M con 30d → score bajo
        _seed(db_session, valor=1_000_000, dr=30)

        r = client.get("/glosas/stats/criticas-economicas")
        d = r.json()
        scores = [it["score_urgencia_economica"] for it in d["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, valor=99_999_999, dr=0, estado="LEVANTADA")
        r = client.get("/glosas/stats/criticas-economicas")
        d = r.json()
        assert d["items"] == []

    def test_excluye_valor_zero(self, client, db_session):
        _seed(db_session, valor=0, dr=0)
        r = client.get("/glosas/stats/criticas-economicas")
        d = r.json()
        assert d["items"] == []

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed(db_session, valor=1000 * (i + 1), dr=i)
        r = client.get("/glosas/stats/criticas-economicas?top=3")
        d = r.json()
        assert len(d["items"]) == 3
