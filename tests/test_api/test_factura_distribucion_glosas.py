"""Tests del endpoint GET /glosas/stats/factura-distribucion-glosas (R306 P1)."""
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


def _seed(db, factura):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestFacturaDistribucion:
    def test_buckets(self, client, db_session):
        # F1 con 1 glosa
        _seed(db_session, "F1")
        # F2 con 3 glosas
        for _ in range(3):
            _seed(db_session, "F2")
        # F3 con 12 glosas
        for _ in range(12):
            _seed(db_session, "F3")

        r = client.get(
            "/glosas/stats/factura-distribucion-glosas"
        )
        d = r.json()
        bm = {b["glosas_por_factura"]: b["count_facturas"]
              for b in d["buckets"]}
        assert bm["1"] == 1
        assert bm["3"] == 1
        assert bm["10+"] == 1
        assert d["total_facturas"] == 3
        assert d["total_glosas"] == 16

    def test_vacio(self, client):
        r = client.get(
            "/glosas/stats/factura-distribucion-glosas"
        )
        d = r.json()
        assert d["total_facturas"] == 0
