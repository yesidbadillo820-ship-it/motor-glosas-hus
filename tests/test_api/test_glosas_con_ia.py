"""Tests del endpoint GET /sistema/glosas-con-ia (R157 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import AICallRecord, GlosaRecord, UsuarioRecord


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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_glosa(db, gid):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_call(db, glosa_id, cost=0.01):
    db.add(AICallRecord(
        proveedor="anthropic", modelo="claude",
        glosa_id=glosa_id, cost_usd=cost,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestGlosasConIA:
    def test_estructura(self, client):
        r = client.get("/sistema/glosas-con-ia")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("ventana_dias", "total_glosas_periodo",
                    "glosas_con_ia", "cobertura_pct",
                    "calls_por_glosa_promedio",
                    "cost_promedio_usd_por_glosa"):
            assert key in d

    def test_sin_glosas(self, client):
        r = client.get("/sistema/glosas-con-ia")
        d = r.json()
        assert d["total_glosas_periodo"] == 0
        assert d["cobertura_pct"] == 0.0

    def test_cobertura_pct(self, client, db_session):
        # 4 glosas, 2 con IA → 50% cobertura
        _seed_glosa(db_session, 1)
        _seed_glosa(db_session, 2)
        _seed_glosa(db_session, 3)
        _seed_glosa(db_session, 4)
        _seed_call(db_session, 1)
        _seed_call(db_session, 2)
        _seed_call(db_session, 2)  # multi-call mismo gid

        r = client.get("/sistema/glosas-con-ia")
        d = r.json()
        assert d["total_glosas_periodo"] == 4
        assert d["glosas_con_ia"] == 2
        assert d["cobertura_pct"] == 50.0

    def test_calls_promedio(self, client, db_session):
        # 1 glosa con 3 calls → 3 calls/glosa
        _seed_glosa(db_session, 1)
        _seed_call(db_session, 1, cost=0.05)
        _seed_call(db_session, 1, cost=0.03)
        _seed_call(db_session, 1, cost=0.02)
        r = client.get("/sistema/glosas-con-ia")
        d = r.json()
        assert d["calls_por_glosa_promedio"] == 3.0
        assert d["cost_total_usd"] == 0.1
