"""Tests del endpoint GET /glosas/stats/prioridad-distribucion (R302 P1)."""
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


def _seed(db, prioridad, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        prioridad=prioridad,
    ))
    db.commit()


class TestPrioridadDistribucion:
    def test_distribucion(self, client, db_session):
        _seed(db_session, "ALTA")
        _seed(db_session, "ALTA")
        _seed(db_session, "NORMAL")
        _seed(db_session, "NORMAL", estado="LEVANTADA")

        r = client.get("/glosas/stats/prioridad-distribucion")
        d = r.json()
        bucket = {it["prioridad"]: it for it in d["items"]}
        assert bucket["ALTA"]["count"] == 2
        assert bucket["ALTA"]["abiertas"] == 2
        assert bucket["NORMAL"]["count"] == 2
        assert bucket["NORMAL"]["abiertas"] == 1
