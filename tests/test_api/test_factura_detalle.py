"""Tests del endpoint GET /glosas/factura-detalle (R204 P1)."""
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


def _seed(db, factura, valor=1000, valor_rec=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=valor, valor_recuperado=valor_rec,
        etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestFacturaDetalle:
    def test_factura_inexistente(self, client):
        r = client.get("/glosas/factura-detalle?factura=NO_EXISTE")
        d = r.json()
        assert d["total_glosas"] == 0

    def test_match_y_totales(self, client, db_session):
        _seed(db_session, "F-1", valor=10_000, valor_rec=5_000)
        _seed(db_session, "F-1", valor=20_000, valor_rec=15_000)
        _seed(db_session, "F-2", valor=999)

        r = client.get("/glosas/factura-detalle?factura=F-1")
        d = r.json()
        assert d["total_glosas"] == 2
        assert d["valor_objetado_total"] == 30_000
        assert d["valor_recuperado_total"] == 20_000

    def test_aislamiento_estricto(self, client, db_session):
        _seed(db_session, "F-1")
        _seed(db_session, "F-12345")  # F-1 NO debe matchear

        r = client.get("/glosas/factura-detalle?factura=F-1")
        d = r.json()
        assert d["total_glosas"] == 1
