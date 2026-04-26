"""Tests del endpoint GET /glosas/stats/conciliaciones-por-eps (R351 P1)."""
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


def _seed_glosa(db, glosa_id, eps):
    db.add(GlosaRecord(
        id=glosa_id,
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


def _seed_concil(db, glosa_id, valor=1000):
    db.add(ConciliacionRecord(
        glosa_id=glosa_id, valor_conciliado=valor,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConciliacionesPorEPS:
    def test_aggrega_por_eps(self, client, db_session):
        _seed_glosa(db_session, 1, "SANITAS")
        _seed_glosa(db_session, 2, "SANITAS")
        _seed_glosa(db_session, 3, "OTRA")
        _seed_concil(db_session, 1, valor=1000)
        _seed_concil(db_session, 2, valor=2000)
        _seed_concil(db_session, 3, valor=500)

        r = client.get("/glosas/stats/conciliaciones-por-eps")
        d = r.json()
        b = {it["eps"]: it for it in d["items"]}
        assert b["SANITAS"]["count_conciliaciones"] == 2
        assert b["SANITAS"]["valor_conciliado_total"] == 3000
        assert b["OTRA"]["count_conciliaciones"] == 1
