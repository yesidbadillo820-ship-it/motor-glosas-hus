"""Tests del endpoint /plantillas-gold/export.json (R77 P1)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import PlantillaGoldRecord, UsuarioRecord


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
def usuario_coord():
    return UsuarioRecord(id=1, email="coord@hus.com", rol="COORDINADOR", activo=1)


def _seed(db, **kw):
    base = dict(
        eps="FAMISANAR", codigo_glosa="TA0201",
        tipo="TA", titulo="X",
        argumento="texto suficientemente largo del argumento ganador con normas",
        usos=5, activa=1, creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(PlantillaGoldRecord(**base))
    db.commit()


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestExportPlantillasGold:
    def test_export_vacio(self, client):
        r = client.get("/plantillas-gold/export.json")
        assert r.status_code == 200
        d = json.loads(r.text)
        assert d["metadata"]["total"] == 0
        assert d["plantillas"] == []

    def test_metadata_incluye_exportado_por(self, client, db_session):
        _seed(db_session, titulo="Test")
        r = client.get("/plantillas-gold/export.json")
        d = json.loads(r.text)
        assert d["metadata"]["exportado_por"] == "coord@hus.com"
        assert d["metadata"]["total"] == 1

    def test_solo_activas_default(self, client, db_session):
        _seed(db_session, titulo="ACTIVA", activa=1)
        _seed(db_session, titulo="INACTIVA", activa=0)
        r = client.get("/plantillas-gold/export.json")
        d = json.loads(r.text)
        titulos = [p["titulo"] for p in d["plantillas"]]
        assert "ACTIVA" in titulos
        assert "INACTIVA" not in titulos

    def test_solo_activas_false_incluye_todas(self, client, db_session):
        _seed(db_session, titulo="ACTIVA", activa=1)
        _seed(db_session, titulo="INACTIVA", activa=0)
        r = client.get("/plantillas-gold/export.json?solo_activas=false")
        d = json.loads(r.text)
        titulos = [p["titulo"] for p in d["plantillas"]]
        assert "ACTIVA" in titulos
        assert "INACTIVA" in titulos

    def test_descarga_attachment(self, client):
        r = client.get("/plantillas-gold/export.json")
        assert r.status_code == 200
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".json" in r.headers.get("content-disposition", "")

    def test_orden_por_usos_desc(self, client, db_session):
        _seed(db_session, titulo="POPULAR", usos=100)
        _seed(db_session, titulo="MEDIA", usos=10)
        _seed(db_session, titulo="POCO", usos=1)
        r = client.get("/plantillas-gold/export.json")
        d = json.loads(r.text)
        titulos = [p["titulo"] for p in d["plantillas"]]
        assert titulos == ["POPULAR", "MEDIA", "POCO"]
