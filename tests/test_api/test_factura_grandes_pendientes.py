"""Tests del endpoint GET /glosas/stats/factura-grandes-pendientes (R362 P1)."""
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


def _seed(db, factura, valor_factura, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        valor_factura=valor_factura,
    ))
    db.commit()


class TestFacturaGrandesPendientes:
    def test_filtra(self, client, db_session):
        _seed(db_session, "F100", valor_factura=60_000_000)
        # Pequeña, no cuenta
        _seed(db_session, "F200", valor_factura=10_000_000)
        # Grande pero todas cerradas, no cuenta
        _seed(
            db_session, "F300", valor_factura=70_000_000,
            estado="LEVANTADA",
        )

        r = client.get(
            "/glosas/stats/factura-grandes-pendientes"
            "?umbral=50000000"
        )
        d = r.json()
        assert d["total_facturas"] == 1
        assert d["items"][0]["factura"] == "F100"
