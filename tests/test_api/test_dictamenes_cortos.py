"""Tests del endpoint GET /glosas/stats/dictamenes-cortos (R166 P1)."""
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


def _seed(db, dictamen, estado="RADICADA"):
    db.add(GlosaRecord(
        eps="X", paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
        dictamen=dictamen,
    ))
    db.commit()


class TestDictamenesCortos:
    def test_estructura(self, client):
        r = client.get("/glosas/stats/dictamenes-cortos")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("umbral_chars", "total_dictamenes_cortos", "items"):
            assert key in d

    def test_detecta_cortos(self, client, db_session):
        # Dictamen corto (50 chars) → aparece
        _seed(db_session, "x" * 50)
        # Dictamen largo (300 chars) → no
        _seed(db_session, "y" * 300)

        r = client.get("/glosas/stats/dictamenes-cortos?umbral_chars=200")
        d = r.json()
        assert d["total_dictamenes_cortos"] == 1

    def test_excluye_cerradas(self, client, db_session):
        _seed(db_session, "x" * 50, estado="LEVANTADA")
        r = client.get("/glosas/stats/dictamenes-cortos?umbral_chars=200")
        d = r.json()
        assert d["items"] == []

    def test_orden_por_chars_asc(self, client, db_session):
        _seed(db_session, "x" * 100)
        _seed(db_session, "x" * 50)
        _seed(db_session, "x" * 150)

        r = client.get("/glosas/stats/dictamenes-cortos?umbral_chars=200")
        d = r.json()
        chars = [it["dictamen_chars"] for it in d["items"]]
        assert chars == sorted(chars)
