"""Tests del endpoint GET /admin/conciliaciones-resultado-distribucion (R312 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
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


def _seed_concil(db, glosa_id, resultado, valor=1000):
    db.add(ConciliacionRecord(
        glosa_id=glosa_id, resultado=resultado,
        valor_conciliado=valor,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestConciliacionesResultadoDistribucion:
    def test_distribucion(self, client, db_session):
        _seed_glosa(db_session, 1)
        _seed_concil(db_session, 1, "FAVORABLE_HUS", 5000)
        _seed_concil(db_session, 1, "FAVORABLE_HUS", 3000)
        _seed_concil(db_session, 1, "PARCIAL", 1000)

        r = client.get(
            "/admin/conciliaciones-resultado-distribucion"
        )
        d = r.json()
        assert d["total_conciliaciones"] == 3
        favorable = next(
            x for x in d["items"]
            if x["resultado"] == "FAVORABLE_HUS"
        )
        assert favorable["count"] == 2
        assert favorable["valor_conciliado_total"] == 8000
