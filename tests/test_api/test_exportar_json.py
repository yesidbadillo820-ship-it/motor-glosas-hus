"""Tests del endpoint GET /glosas/exportar-json (R92 P1, NDJSON)."""
from __future__ import annotations

import json

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
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestExportarJson:
    def test_vacio(self, client):
        r = client.get("/glosas/exportar-json")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/x-ndjson")
        assert r.text == ""

    def test_streamea_ndjson(self, client, db_session):
        _seed(db_session, eps="SANITAS", paciente="Pedro", valor_objetado=5000)
        _seed(db_session, eps="NUEVA EPS", paciente="Ana", valor_objetado=8000)

        r = client.get("/glosas/exportar-json")
        assert r.status_code == 200
        # Cada línea debe ser JSON parseable independientemente
        lines = [l for l in r.text.strip().split("\n") if l]
        assert len(lines) == 2
        objs = [json.loads(l) for l in lines]
        epss = {o["eps"] for o in objs}
        assert epss == {"SANITAS", "NUEVA EPS"}

    def test_estructura_objeto(self, client, db_session):
        _seed(db_session, eps="X", valor_objetado=1234.56)
        r = client.get("/glosas/exportar-json")
        obj = json.loads(r.text.strip())
        assert "id" in obj
        assert "creado_en" in obj
        assert "eps" in obj
        assert obj["eps"] == "X"
        assert obj["valor_objetado"] == 1234.56

    def test_filtro_por_eps(self, client, db_session):
        _seed(db_session, eps="SANITAS")
        _seed(db_session, eps="SANITAS")
        _seed(db_session, eps="NUEVA EPS")

        r = client.get("/glosas/exportar-json?eps=SANITAS")
        lines = [l for l in r.text.strip().split("\n") if l]
        objs = [json.loads(l) for l in lines]
        assert all(o["eps"] == "SANITAS" for o in objs)

    def test_content_disposition_attachment(self, client, db_session):
        _seed(db_session)
        r = client.get("/glosas/exportar-json")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".ndjson" in cd
