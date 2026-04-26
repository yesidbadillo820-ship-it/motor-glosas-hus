"""Tests del endpoint GET /glosas/stats/conciliaciones-top-monto (R340 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    ConciliacionRecord,
    GlosaRecord,
    UsuarioRecord,
)


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


def _seed_glosa(db, glosa_id):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concil(db, glosa_id, valor):
    db.add(ConciliacionRecord(
        glosa_id=glosa_id, valor_conciliado=valor,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConciliacionesTopMonto:
    def test_orden(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_concil(db_session, 1, 1000)
        _seed_concil(db_session, 1, 5000)
        _seed_concil(db_session, 1, 3000)

        r = client.get("/glosas/stats/conciliaciones-top-monto")
        d = r.json()
        valores = [it["valor_conciliado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
        assert valores[0] == 5000

    def test_limit(self, client, db_session):
        _seed_glosa(db_session, 1)
        for v in [100, 200, 300, 400, 500]:
            _seed_concil(db_session, 1, v)
        r = client.get(
            "/glosas/stats/conciliaciones-top-monto?limit=2"
        )
        d = r.json()
        assert len(d["items"]) == 2
