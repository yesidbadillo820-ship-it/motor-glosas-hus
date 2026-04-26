"""Tests del endpoint GET /glosas/stats/facturas-saldos-pendientes (R269 P1)."""
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


def _seed(db, factura, saldo, estado="RADICADA", eps="X"):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        saldo_factura=saldo,
        valor_factura=10_000,
    ))
    db.commit()


class TestFacturasSaldosPendientes:
    def test_orden_desc(self, client, db_session):
        _seed(db_session, "F100", saldo=5_000)
        _seed(db_session, "F200", saldo=20_000)
        _seed(db_session, "F300", saldo=10_000)
        r = client.get("/glosas/stats/facturas-saldos-pendientes")
        d = r.json()
        saldos = [it["saldo_factura"] for it in d["items"]]
        assert saldos == sorted(saldos, reverse=True)
        assert d["items"][0]["factura"] == "F200"

    def test_excluye_si_todas_cerradas(self, client, db_session):
        _seed(db_session, "F999", saldo=99_999, estado="LEVANTADA")
        r = client.get("/glosas/stats/facturas-saldos-pendientes")
        d = r.json()
        assert d["items"] == []

    def test_count_abiertas(self, client, db_session):
        _seed(db_session, "F1", saldo=100, estado="RADICADA")
        _seed(db_session, "F1", saldo=100, estado="LEVANTADA")
        _seed(db_session, "F1", saldo=100, estado="RADICADA")
        r = client.get("/glosas/stats/facturas-saldos-pendientes")
        d = r.json()
        item = d["items"][0]
        assert item["count_glosas"] == 3
        assert item["count_abiertas"] == 2
