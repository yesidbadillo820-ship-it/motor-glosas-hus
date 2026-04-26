"""Tests del endpoint GET /glosas/stats/eps-codigo-pareto (R268 P1)."""
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


def _seed(db, eps, codigo, valor):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSCodigoPareto:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/eps-codigo-pareto")
        d = r.json()
        assert d["valor_total"] == 0
        assert d["parejas_top80"] == []

    def test_concentracion(self, client, db_session):
        # (SANITAS, TA0801) → 80
        _seed(db_session, "SANITAS", "TA0801", 80)
        # (EPS001, FA0603) → 10
        _seed(db_session, "EPS001", "FA0603", 10)
        # (EPS002, RA0001) → 10
        _seed(db_session, "EPS002", "RA0001", 10)

        r = client.get("/glosas/stats/eps-codigo-pareto")
        d = r.json()
        assert d["valor_total"] == 100
        # Solo 1 pareja debería estar en top80 (acumula 80% sola)
        assert d["count_parejas_top80"] == 1
        assert d["parejas_top80"][0]["eps"] == "SANITAS"
        assert d["parejas_top80"][0]["codigo_glosa"] == "TA0801"
        assert d["parejas_top80"][0]["pct_individual"] == 80.0
