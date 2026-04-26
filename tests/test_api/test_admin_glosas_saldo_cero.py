"""Tests del endpoint GET /admin/glosas-saldo-cero-detalle (R360 P1)."""
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
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1,
    )


@pytest.fixture
def client(db_session, admin_user):
    from app.api.deps import get_usuario_actual
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed(db, saldo, valor_factura=10000, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        saldo_factura=saldo,
        valor_factura=valor_factura,
    ))
    db.commit()


class TestGlosasSaldoCero:
    def test_filtra(self, client, db_session):
        _seed(db_session, saldo=0, valor_factura=10000)
        _seed(db_session, saldo=None, valor_factura=10000)
        _seed(db_session, saldo=5000, valor_factura=10000)  # OK
        _seed(db_session, saldo=0, valor_factura=10000,
              estado="LEVANTADA")  # cerrada

        r = client.get("/admin/glosas-saldo-cero-detalle")
        d = r.json()
        assert d["total_glosas_anomalas"] == 2
