"""Tests del endpoint GET /glosas/stats/glosas-grandes-perdidas (R330 P1)."""
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


def _seed(db, valor, estado="RATIFICADA", aceptado=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, valor_aceptado=aceptado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestGlosasGrandesPerdidas:
    def test_filtra(self, client, db_session):
        _seed(db_session, valor=10_000_000, aceptado=10_000_000)
        _seed(db_session, valor=1_000_000, aceptado=1_000_000)
        _seed(
            db_session, valor=20_000_000, estado="LEVANTADA",
        )

        r = client.get(
            "/glosas/stats/glosas-grandes-perdidas?umbral=5000000"
        )
        d = r.json()
        assert d["total_grandes_perdidas"] == 1
        assert d["valor_total_perdido"] == 10_000_000

    def test_orden_desc(self, client, db_session):
        _seed(db_session, valor=10_000_000)
        _seed(db_session, valor=20_000_000)
        r = client.get(
            "/glosas/stats/glosas-grandes-perdidas?umbral=5000000"
        )
        d = r.json()
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
