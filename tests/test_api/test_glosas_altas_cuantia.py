"""Tests del endpoint GET /glosas/stats/glosas-altas-cuantia (R253 P1)."""
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


def _seed(db, valor, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestGlosasAltasCuantia:
    def test_umbral(self, client, db_session):
        # Solo 10M debería pasar el default 5M
        _seed(db_session, valor=10_000_000)
        _seed(db_session, valor=1_000_000)

        r = client.get("/glosas/stats/glosas-altas-cuantia")
        d = r.json()
        assert d["total_altas_cuantia"] == 1
        assert d["items"][0]["valor_objetado"] == 10_000_000

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, valor=99_999_999, estado="LEVANTADA")
        r = client.get("/glosas/stats/glosas-altas-cuantia")
        d = r.json()
        assert d["items"] == []

    def test_orden_desc(self, client, db_session):
        _seed(db_session, valor=10_000_000)
        _seed(db_session, valor=20_000_000)
        _seed(db_session, valor=15_000_000)
        r = client.get("/glosas/stats/glosas-altas-cuantia")
        d = r.json()
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
