"""Tests del endpoint GET /glosas/top-valor (R183 P1)."""
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


def _seed(db, valor, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestTopValor:
    def test_estructura(self, client):
        r = client.get("/glosas/top-valor")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("top_solicitado", "abiertas_only", "items"):
            assert key in d

    def test_orden_valor_desc(self, client, db_session):
        _seed(db_session, valor=100)
        _seed(db_session, valor=10000)
        _seed(db_session, valor=500)

        r = client.get("/glosas/top-valor")
        d = r.json()
        valores = [it["valor_objetado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
        assert d["items"][0]["valor_objetado"] == 10000

    def test_excluye_cerradas_por_default(self, client, db_session):
        _seed(db_session, valor=99999, estado="LEVANTADA")
        _seed(db_session, valor=100, estado="RADICADA")

        r = client.get("/glosas/top-valor")
        d = r.json()
        # Solo la abierta
        assert len(d["items"]) == 1

    def test_incluye_cerradas_si_se_pide(self, client, db_session):
        _seed(db_session, valor=99999, estado="LEVANTADA")
        _seed(db_session, valor=100, estado="RADICADA")

        r = client.get("/glosas/top-valor?abiertas_only=false")
        d = r.json()
        assert len(d["items"]) == 2

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed(db_session, valor=1000 * i)
        r = client.get("/glosas/top-valor?top=3")
        d = r.json()
        assert len(d["items"]) == 3
