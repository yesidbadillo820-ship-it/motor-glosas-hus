"""Tests del endpoint GET /glosas/stats/facturas-hot (R124 P1)."""
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


def _seed(db, factura, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(factura=factura, **base))
    db.commit()


class TestFacturasHot:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/facturas-hot")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_factura_unica_no_aparece(self, client, db_session):
        # min_glosas default = 3
        _seed(db_session, "F-1")
        _seed(db_session, "F-1")
        r = client.get("/glosas/stats/facturas-hot")
        d = r.json()
        assert d["items"] == []

    def test_factura_caliente(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "F-HOT", codigo_glosa="TA0201")
        r = client.get("/glosas/stats/facturas-hot")
        d = r.json()
        assert len(d["items"]) == 1
        assert d["items"][0]["factura"] == "F-HOT"
        assert d["items"][0]["count_glosas"] == 5

    def test_excluye_factura_NA(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "N/A")
        r = client.get("/glosas/stats/facturas-hot")
        d = r.json()
        assert d["items"] == []

    def test_estados_y_codigos_distintos(self, client, db_session):
        _seed(db_session, "F-1", codigo_glosa="TA", estado="RADICADA")
        _seed(db_session, "F-1", codigo_glosa="FA", estado="RADICADA")
        _seed(db_session, "F-1", codigo_glosa="TA", estado="LEVANTADA")

        r = client.get("/glosas/stats/facturas-hot")
        d = r.json()
        item = d["items"][0]
        assert item["estados"] == {"RADICADA": 2, "LEVANTADA": 1}
        assert item["codigos_distintos"] == ["FA", "TA"]

    def test_orden_por_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "MUCHAS")
        for _ in range(3):
            _seed(db_session, "POCAS")
        r = client.get("/glosas/stats/facturas-hot")
        d = r.json()
        assert d["items"][0]["factura"] == "MUCHAS"
        assert d["items"][0]["count_glosas"] == 5
        assert d["items"][1]["factura"] == "POCAS"
