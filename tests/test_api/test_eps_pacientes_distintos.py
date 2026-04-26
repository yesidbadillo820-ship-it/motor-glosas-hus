"""Tests del endpoint GET /glosas/stats/eps-pacientes-distintos (R321 P1)."""
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


def _seed(db, eps, paciente):
    db.add(GlosaRecord(
        eps=eps, paciente=paciente, codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEPSPacientesDistintos:
    def test_distintos(self, client, db_session):
        _seed(db_session, "X", "P1")
        _seed(db_session, "X", "P2")
        _seed(db_session, "X", "P1")  # paciente repetido
        # 3 glosas, 2 pacientes distintos, ratio 1.5

        r = client.get(
            "/glosas/stats/eps-pacientes-distintos?min_glosas=1"
        )
        d = r.json()
        item = d["items"][0]
        assert item["count_glosas"] == 3
        assert item["pacientes_distintos"] == 2
        assert item["ratio_glosas_paciente"] == 1.5
