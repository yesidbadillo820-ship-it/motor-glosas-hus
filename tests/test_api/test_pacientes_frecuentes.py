"""Tests del endpoint GET /glosas/stats/pacientes-frecuentes (R141 P1)."""
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


def _seed(db, paciente, **kw):
    base = dict(
        eps="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(), factura="F-1",
    )
    base.update(kw)
    db.add(GlosaRecord(paciente=paciente, **base))
    db.commit()


class TestPacientesFrecuentes:
    def test_vacio(self, client):
        r = client.get("/glosas/stats/pacientes-frecuentes")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["items"] == []

    def test_paciente_unico_no_aparece(self, client, db_session):
        _seed(db_session, "Pedro")  # solo 1 glosa
        r = client.get("/glosas/stats/pacientes-frecuentes")
        d = r.json()
        # min_glosas=2, Pedro tiene solo 1 → no aparece
        assert d["items"] == []

    def test_paciente_recurrente(self, client, db_session):
        _seed(db_session, "Ana", factura="F-1", eps="SANITAS")
        _seed(db_session, "Ana", factura="F-2", eps="SANITAS")
        _seed(db_session, "Ana", factura="F-3", eps="NUEVA EPS")

        r = client.get("/glosas/stats/pacientes-frecuentes")
        d = r.json()
        assert d["items"][0]["paciente"] == "Ana"
        assert d["items"][0]["count_glosas"] == 3
        assert d["items"][0]["facturas_distintas"] == 3
        assert d["items"][0]["eps_distintas"] == 2

    def test_orden_por_count_desc(self, client, db_session):
        for _ in range(5):
            _seed(db_session, "Mucho")
        for _ in range(2):
            _seed(db_session, "Poco")

        r = client.get("/glosas/stats/pacientes-frecuentes")
        d = r.json()
        assert d["items"][0]["paciente"] == "Mucho"
        assert d["items"][1]["paciente"] == "Poco"

    def test_min_glosas_custom(self, client, db_session):
        for _ in range(3):
            _seed(db_session, "Tres")
        for _ in range(2):
            _seed(db_session, "Dos")

        # min_glosas=3 → solo "Tres"
        r = client.get("/glosas/stats/pacientes-frecuentes?min_glosas=3")
        d = r.json()
        nombres = [it["paciente"] for it in d["items"]]
        assert "Tres" in nombres
        assert "Dos" not in nombres
