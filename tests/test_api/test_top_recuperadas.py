"""Tests del endpoint GET /glosas/top-recuperadas (R189 P1)."""
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


def _seed(db, valor_rec, estado="LEVANTADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=10000, valor_recuperado=valor_rec,
        etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestTopRecuperadas:
    def test_estructura(self, client):
        r = client.get("/glosas/top-recuperadas")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("top_solicitado", "items"):
            assert key in d

    def test_excluye_sin_recuperacion(self, client, db_session):
        _seed(db_session, valor_rec=0)  # sin recuperar
        r = client.get("/glosas/top-recuperadas")
        d = r.json()
        assert d["items"] == []

    def test_orden_desc(self, client, db_session):
        _seed(db_session, valor_rec=1000)
        _seed(db_session, valor_rec=10000)
        _seed(db_session, valor_rec=500)
        r = client.get("/glosas/top-recuperadas")
        d = r.json()
        valores = [it["valor_recuperado"] for it in d["items"]]
        assert valores == sorted(valores, reverse=True)
        assert d["items"][0]["valor_recuperado"] == 10000

    def test_top_limita(self, client, db_session):
        for i in range(10):
            _seed(db_session, valor_rec=1000 * (i + 1))
        r = client.get("/glosas/top-recuperadas?top=3")
        d = r.json()
        assert len(d["items"]) == 3
