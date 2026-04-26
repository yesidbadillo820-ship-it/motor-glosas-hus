"""Tests del endpoint GET /glosas/stats/dashboard-completo (R225 P1)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestDashboardCompleto:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/dashboard-completo")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("kpis_globales", "urgencia",
                    "top_3_eps_pendientes", "actividad_hoy"):
            assert key in d
        for k in ("total_glosas", "abiertas", "valor_pendiente",
                  "valor_recuperado_acumulado"):
            assert k in d["kpis_globales"]
        for k in ("VENCIDA", "CRITICA", "PROXIMA", "LEJANA"):
            assert k in d["urgencia"]

    def test_kpis_correctos(self, client, db_session):
        _seed(db_session, eps="A", valor_objetado=10_000, dias_restantes=20)
        _seed(db_session, eps="A", valor_objetado=5_000, dias_restantes=2)
        _seed(db_session, eps="B", valor_objetado=3_000, dias_restantes=-5)

        r = client.get("/glosas/stats/dashboard-completo")
        d = r.json()
        assert d["kpis_globales"]["abiertas"] == 3
        assert d["urgencia"]["LEJANA"] == 1
        assert d["urgencia"]["CRITICA"] == 1
        assert d["urgencia"]["VENCIDA"] == 1
        # Top 3: A=15k, B=3k
        assert d["top_3_eps_pendientes"][0]["eps"] == "A"
