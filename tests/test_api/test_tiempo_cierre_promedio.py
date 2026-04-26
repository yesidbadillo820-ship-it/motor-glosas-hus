"""Tests del endpoint GET /glosas/stats/tiempo-cierre-promedio (R245 P1)."""
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


def _seed(db, dias_a_cierre):
    cre = ahora_utc() - timedelta(days=dias_a_cierre + 30)
    dec = cre + timedelta(days=dias_a_cierre)
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=cre, fecha_decision_eps=dec,
    ))
    db.commit()


class TestTiempoCierrePromedio:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/tiempo-cierre-promedio")
        d = r.json()
        for key in ("count_glosas_cerradas",
                    "tiempo_promedio_dias",
                    "tiempo_mediano_dias",
                    "tiempo_max_dias"):
            assert key in d

    def test_promedio(self, client, db_session):
        _seed(db_session, 10)
        _seed(db_session, 20)
        _seed(db_session, 30)
        # promedio = 20

        r = client.get("/glosas/stats/tiempo-cierre-promedio")
        d = r.json()
        assert d["count_glosas_cerradas"] == 3
        assert d["tiempo_promedio_dias"] == 20.0
        assert d["tiempo_mediano_dias"] == 20.0
        assert d["tiempo_max_dias"] == 30
