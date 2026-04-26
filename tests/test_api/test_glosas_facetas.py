"""Tests del endpoint GET /glosas/facetas (R88 P1)."""
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
        eps="X", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100, etapa="RESPUESTA_PRIMERA", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestGlosasFacetas:
    def test_vacio(self, client):
        r = client.get("/glosas/facetas")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d == {
            "eps": [], "etapas": [], "estados": [],
            "codigos_glosa": [], "gestores": [],
        }

    def test_distinct_y_ordenado(self, client, db_session):
        _seed(db_session, eps="SANITAS", codigo_glosa="TA0201",
              etapa="A", estado="RADICADA", gestor_nombre="Ana")
        _seed(db_session, eps="SANITAS", codigo_glosa="TA0201",
              etapa="A", estado="RADICADA", gestor_nombre="Ana")  # duplicado
        _seed(db_session, eps="NUEVA EPS", codigo_glosa="FA0603",
              etapa="B", estado="ACEPTADA", gestor_nombre="Bruno")

        r = client.get("/glosas/facetas")
        d = r.json()
        # Cada valor aparece UNA vez y ordenado alfabéticamente
        assert d["eps"] == ["NUEVA EPS", "SANITAS"]
        assert d["etapas"] == ["A", "B"]
        assert d["estados"] == ["ACEPTADA", "RADICADA"]
        assert d["codigos_glosa"] == ["FA0603", "TA0201"]
        assert d["gestores"] == ["Ana", "Bruno"]

    def test_excluye_nulos(self, client, db_session):
        # Una glosa con gestor_nombre=None — no debe aparecer en la lista
        _seed(db_session, eps="X", gestor_nombre=None)
        _seed(db_session, eps="X", gestor_nombre="Carla")
        r = client.get("/glosas/facetas")
        d = r.json()
        assert d["gestores"] == ["Carla"]
