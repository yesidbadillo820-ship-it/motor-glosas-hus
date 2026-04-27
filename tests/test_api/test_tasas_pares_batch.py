"""Tests del endpoint POST /glosas/stats/tasas-pares-batch (R382 P1)."""
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
    return UsuarioRecord(id=1, email="x@x", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, gid, eps="X", codigo="C", estado="RADICADA"):
    db.add(GlosaRecord(
        id=gid,
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestTasasParesBatch:
    def test_calcula_tasas(self, client, db_session):
        _seed(db_session, 1, eps="X", codigo="C")
        # Histórico (X, C): 2 LEV / 3 dec
        _seed(db_session, 100, estado="LEVANTADA")
        _seed(db_session, 101, estado="LEVANTADA")
        _seed(db_session, 102, estado="RATIFICADA")

        r = client.post(
            "/glosas/stats/tasas-pares-batch",
            json={"glosa_ids": [1]},
        )
        d = r.json()
        item = d["items"][0]
        assert item["glosa_id"] == 1
        # 2/3 ≈ 66.67%
        assert item["tasa_par_pct"] == 66.67
        assert item["n_par"] == 3

    def test_sin_muestras(self, client, db_session):
        _seed(db_session, 1)
        r = client.post(
            "/glosas/stats/tasas-pares-batch",
            json={"glosa_ids": [1]},
        )
        d = r.json()
        assert d["items"][0]["tasa_par_pct"] is None

    def test_lista_vacia(self, client):
        r = client.post(
            "/glosas/stats/tasas-pares-batch",
            json={"glosa_ids": []},
        )
        d = r.json()
        assert d["items"] == []
