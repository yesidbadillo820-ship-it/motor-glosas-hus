"""Tests del endpoint GET /glosas/stats/dictamenes-largos-top (R314 P1)."""
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


def _seed(db, dictamen):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="LEVANTADA",
        creado_en=ahora_utc(),
        dictamen=dictamen,
    ))
    db.commit()


class TestDictamenesLargosTop:
    def test_filtra_y_ordena(self, client, db_session):
        _seed(db_session, "x" * 100)
        _seed(db_session, "y" * 500)
        _seed(db_session, "corto")  # < 50

        r = client.get("/glosas/stats/dictamenes-largos-top")
        d = r.json()
        # Solo dos pasaron filtro de 50+
        assert d["total_glosas_evaluadas"] == 2
        # Más largo primero
        assert d["items"][0]["dictamen_len"] == 500
        assert d["items"][1]["dictamen_len"] == 100

    def test_limit(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "x" * 100)
        r = client.get("/glosas/stats/dictamenes-largos-top?limit=2")
        d = r.json()
        assert len(d["items"]) == 2
