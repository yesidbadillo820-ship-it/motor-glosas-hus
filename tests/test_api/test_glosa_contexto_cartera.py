"""Tests del endpoint GET /glosas/{id}/contexto-cartera (R280 P1)."""
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


def _seed(db, glosa_id, factura, estado="RADICADA", valor=1000,
          saldo=0, valor_factura=0):
    db.add(GlosaRecord(
        id=glosa_id,
        eps="X", paciente="X", codigo_glosa="C", factura=factura,
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        saldo_factura=saldo,
        valor_factura=valor_factura,
    ))
    db.commit()


class TestContextoCartera:
    def test_factura_con_varias_glosas(self, client, db_session):
        _seed(db_session, 1, "F100", valor=1000, saldo=5000,
              valor_factura=20000)
        _seed(db_session, 2, "F100", valor=2000, estado="LEVANTADA")
        _seed(db_session, 3, "F100", valor=3000, estado="RADICADA")

        r = client.get("/glosas/1/contexto-cartera")
        d = r.json()
        assert d["glosa_id"] == 1
        assert d["valor_factura"] == 20000
        assert d["saldo_factura"] == 5000
        assert d["factura_resumen"]["count_glosas"] == 3
        assert d["factura_resumen"]["valor_objetado_total"] == 6000
        # Abierto: glosa 1 (RADICADA) + glosa 3 (RADICADA) = 4000
        assert d["factura_resumen"]["valor_objetado_abierto"] == 4000

    def test_404(self, client):
        r = client.get("/glosas/999/contexto-cartera")
        assert r.status_code == 404
