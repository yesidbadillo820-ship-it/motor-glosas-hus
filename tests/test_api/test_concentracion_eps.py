"""Tests del endpoint GET /glosas/stats/concentracion-eps (R187 P1)."""
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


def _seed(db, eps, valor):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConcentracionEPS:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/concentracion-eps")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_eps", "valor_pendiente_total", "hhi",
                    "top_eps_pct", "top_3_eps_pct",
                    "interpretacion"):
            assert key in d

    def test_alto_riesgo_monopolio(self, client, db_session):
        # Solo SANITAS → HHI = 10000
        _seed(db_session, "SANITAS", 1_000_000)
        r = client.get("/glosas/stats/concentracion-eps")
        d = r.json()
        assert d["hhi"] == 10000.0
        assert d["top_eps_pct"] == 100.0
        assert d["interpretacion"] == "ALTO_RIESGO"

    def test_poco_concentrado(self, client, db_session):
        # 10 EPS por igual: cada una 10% → HHI = 1000
        for i in range(10):
            _seed(db_session, f"EPS_{i}", 100_000)
        r = client.get("/glosas/stats/concentracion-eps")
        d = r.json()
        # HHI = 10 × (10%)² × 10000 = 10 × 0.01 × 10000 = 1000
        assert d["hhi"] == 1000.0
        assert d["interpretacion"] == "POCO_CONCENTRADO"

    def test_top_3_pct(self, client, db_session):
        _seed(db_session, "A", 50)
        _seed(db_session, "B", 30)
        _seed(db_session, "C", 10)
        _seed(db_session, "D", 5)
        _seed(db_session, "E", 5)
        # Top 3 = 50+30+10 = 90 / 100 = 90%
        r = client.get("/glosas/stats/concentracion-eps")
        d = r.json()
        assert d["top_3_eps_pct"] == 90.0
