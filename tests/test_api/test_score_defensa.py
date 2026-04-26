"""Tests del endpoint GET /glosas/{id}/score-defensa (R185 P1)."""
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


def _seed(db, gid=None, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    if gid is not None:
        base["id"] = gid
    db.add(GlosaRecord(**base))
    db.commit()


class TestScoreDefensa:
    def test_404(self, client):
        r = client.get("/glosas/99999/score-defensa")
        assert r.status_code == 404

    def test_estructura(self, client, db_session):
        _seed(db_session, gid=1, dias_restantes=10)
        r = client.get("/glosas/1/score-defensa")
        d = r.json()
        for key in ("glosa_id", "score", "veredicto", "razones"):
            assert key in d
        assert 0 <= d["score"] <= 5
        assert d["veredicto"] in (
            "PROBABLE_DEFENSA", "INCIERTA", "PROBABLE_RATIFICACION",
        )

    def test_score_alto_probable_defensa(self, client, db_session):
        # Glosa target con dictamen + código respuesta + tiempo
        _seed(db_session, gid=1,
              eps="SANITAS", codigo_glosa="TA0201",
              dias_restantes=10,
              codigo_respuesta="RE9901",
              dictamen="x" * 500)
        # Histórico SANITAS+TA0201: alta tasa
        for _ in range(5):
            _seed(db_session, eps="SANITAS", codigo_glosa="TA0201",
                  estado="LEVANTADA")

        r = client.get("/glosas/1/score-defensa")
        d = r.json()
        # Debe tener score alto (>=4)
        assert d["score"] >= 4

    def test_score_bajo_vencida(self, client, db_session):
        _seed(db_session, gid=1, dias_restantes=-30)
        r = client.get("/glosas/1/score-defensa")
        d = r.json()
        # Vencida sin dictamen → score bajo
        assert d["veredicto"] in (
            "INCIERTA", "PROBABLE_RATIFICACION",
        )
