"""Tests del endpoint GET /glosas/stats/edad-promedio-por-estado (R324 P1)."""
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


def _seed(db, estado, dias_atras):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc() - timedelta(days=dias_atras),
    ))
    db.commit()


class TestEdadPromedioPorEstado:
    def test_calcula(self, client, db_session):
        _seed(db_session, "RADICADA", dias_atras=10)
        _seed(db_session, "RADICADA", dias_atras=20)
        # Promedio: 15
        _seed(db_session, "LEVANTADA", dias_atras=5)

        r = client.get("/glosas/stats/edad-promedio-por-estado")
        d = r.json()
        rad = next(x for x in d["items"] if x["estado"] == "RADICADA")
        lev = next(x for x in d["items"] if x["estado"] == "LEVANTADA")
        assert rad["count"] == 2
        assert rad["edad_promedio_dias"] == 15.0
        assert lev["count"] == 1
        assert lev["edad_promedio_dias"] == 5.0
