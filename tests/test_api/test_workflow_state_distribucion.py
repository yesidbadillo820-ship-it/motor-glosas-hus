"""Tests del endpoint GET /glosas/stats/workflow-state-distribucion (R301 P1)."""
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


def _seed(db, workflow_state, valor=1000):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        workflow_state=workflow_state,
    ))
    db.commit()


class TestWorkflowStateDistribucion:
    def test_distribucion(self, client, db_session):
        _seed(db_session, "BORRADOR")
        _seed(db_session, "BORRADOR")
        _seed(db_session, "EN_ANALISIS")

        r = client.get("/glosas/stats/workflow-state-distribucion")
        d = r.json()
        assert d["total_glosas"] == 3
        states = {it["workflow_state"]: it for it in d["items"]}
        assert states["BORRADOR"]["count"] == 2
        assert states["EN_ANALISIS"]["count"] == 1

    def test_vacio(self, client):
        r = client.get("/glosas/stats/workflow-state-distribucion")
        d = r.json()
        assert d["total_glosas"] == 0
