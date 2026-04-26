"""Tests del endpoint GET /glosas/stats/factura-resumen (R325 P1)."""
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


def _seed(db, factura, estado="RADICADA", valor=1000, recuperado=0):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=valor, valor_recuperado=recuperado,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestFacturaResumen:
    def test_drilldown(self, client, db_session):
        _seed(db_session, "F100", estado="RADICADA", valor=2000)
        _seed(
            db_session, "F100", estado="LEVANTADA",
            valor=3000, recuperado=2500,
        )
        _seed(db_session, "OTRA", estado="RADICADA")

        r = client.get(
            "/glosas/stats/factura-resumen?factura=F100"
        )
        d = r.json()
        assert d["factura"] == "F100"
        assert d["count_total"] == 2
        assert d["count_abiertas"] == 1
        assert d["count_cerradas"] == 1
        assert d["valor_objetado_total"] == 5000
        assert d["valor_recuperado_total"] == 2500
        assert len(d["glosas"]) == 2

    def test_factura_inexistente(self, client):
        r = client.get(
            "/glosas/stats/factura-resumen?factura=NOEXISTE"
        )
        d = r.json()
        assert d["count_total"] == 0
