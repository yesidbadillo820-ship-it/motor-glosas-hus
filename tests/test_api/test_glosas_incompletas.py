"""Tests del endpoint GET /glosas/incompletas (R96 P2)."""
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


def _seed(db, **kw):
    base = dict(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
        texto_glosa_original="texto",
        dictamen="<p>" + "x" * 100 + "</p>",
        factura="F-001",
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()
    return db.query(GlosaRecord).order_by(GlosaRecord.id.desc()).first()


class TestGlosasIncompletas:
    def test_vacio(self, client):
        r = client.get("/glosas/incompletas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_incompletas"] == 0
        assert d["items"] == []

    def test_glosa_completa_no_aparece(self, client, db_session):
        _seed(db_session)  # tiene todo
        r = client.get("/glosas/incompletas")
        d = r.json()
        assert d["total_incompletas"] == 0

    def test_detecta_factura_NA(self, client, db_session):
        _seed(db_session, factura="N/A")
        r = client.get("/glosas/incompletas")
        d = r.json()
        assert d["total_incompletas"] == 1
        assert "factura" in d["items"][0]["campos_faltantes"]

    def test_detecta_dictamen_corto(self, client, db_session):
        _seed(db_session, dictamen="muy corto")
        r = client.get("/glosas/incompletas")
        d = r.json()
        assert d["total_incompletas"] == 1
        assert "dictamen" in d["items"][0]["campos_faltantes"]

    def test_detecta_valor_cero(self, client, db_session):
        _seed(db_session, valor_objetado=0)
        r = client.get("/glosas/incompletas")
        d = r.json()
        assert d["total_incompletas"] == 1
        assert "valor_objetado" in d["items"][0]["campos_faltantes"]

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, factura="N/A", estado="ACEPTADA")
        _seed(db_session, factura="N/A", estado="LEVANTADA")
        r = client.get("/glosas/incompletas")
        d = r.json()
        assert d["total_incompletas"] == 0

    def test_orden_por_total_huecos_desc(self, client, db_session):
        # Glosa con 1 hueco
        _seed(db_session, factura="N/A")
        # Glosa con 3 huecos
        _seed(db_session, factura="N/A", valor_objetado=0,
              texto_glosa_original=None)
        r = client.get("/glosas/incompletas")
        d = r.json()
        # Primera debe ser la de 3 huecos
        assert d["items"][0]["total_huecos"] == 3
        assert d["items"][1]["total_huecos"] == 1
