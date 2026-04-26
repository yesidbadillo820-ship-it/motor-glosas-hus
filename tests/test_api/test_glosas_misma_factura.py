"""Tests del endpoint GET /glosas/{id}/glosas-misma-factura (R234 P1)."""
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


def _seed(db, gid, factura="F-1"):
    db.add(GlosaRecord(
        id=gid, eps="X", paciente="X", codigo_glosa="C",
        factura=factura,
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestGlosasMismaFactura:
    def test_404(self, client):
        r = client.get("/glosas/99999/glosas-misma-factura")
        assert r.status_code == 404

    def test_factura_NA(self, client, db_session):
        _seed(db_session, 1, factura="N/A")
        r = client.get("/glosas/1/glosas-misma-factura")
        d = r.json()
        assert d["total_hermanas"] == 0

    def test_excluye_self(self, client, db_session):
        _seed(db_session, 1, factura="F-1")
        _seed(db_session, 2, factura="F-1")
        _seed(db_session, 3, factura="F-1")

        r = client.get("/glosas/1/glosas-misma-factura")
        d = r.json()
        # 2 hermanas (sin self)
        assert d["total_hermanas"] == 2
        ids = [it["id"] for it in d["items"]]
        assert 1 not in ids

    def test_aislamiento(self, client, db_session):
        _seed(db_session, 1, factura="F-1")
        _seed(db_session, 2, factura="F-2")

        r = client.get("/glosas/1/glosas-misma-factura")
        d = r.json()
        assert d["total_hermanas"] == 0
