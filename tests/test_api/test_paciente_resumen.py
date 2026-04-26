"""Tests del endpoint GET /glosas/paciente-resumen (R130 P1)."""
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
        factura="F-001", creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(paciente=paciente, **base))
    db.commit()


class TestPacienteResumen:
    def test_query_minima(self, client):
        # min_length=2
        r = client.get("/glosas/paciente-resumen?paciente=A")
        assert r.status_code == 422

    def test_paciente_no_encontrado(self, client):
        r = client.get("/glosas/paciente-resumen?paciente=Inexistente")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_glosas"] == 0
        assert d["glosas"] == []

    def test_busqueda_case_insensitive(self, client, db_session):
        _seed(db_session, "Pedro Pérez")
        r = client.get("/glosas/paciente-resumen?paciente=pedro")
        d = r.json()
        assert d["total_glosas"] == 1

    def test_resumen_metricas(self, client, db_session):
        _seed(db_session, "Ana López", factura="F-1", eps="SANITAS",
              valor_objetado=10000, valor_recuperado=8000,
              estado="LEVANTADA")
        _seed(db_session, "Ana López", factura="F-2", eps="NUEVA EPS",
              valor_objetado=5000, valor_recuperado=0,
              estado="ACEPTADA")

        r = client.get("/glosas/paciente-resumen?paciente=Ana")
        d = r.json()
        assert d["total_glosas"] == 2
        assert d["facturas_distintas"] == 2
        assert d["eps_distintas"] == 2
        assert d["valor_objetado_total"] == 15000
        assert d["valor_recuperado_total"] == 8000
        assert d["estados"] == {"LEVANTADA": 1, "ACEPTADA": 1}

    def test_excluye_factura_NA_de_distintas(self, client, db_session):
        _seed(db_session, "Juan", factura="N/A")
        _seed(db_session, "Juan", factura="N/A")
        r = client.get("/glosas/paciente-resumen?paciente=Juan")
        d = r.json()
        # 2 glosas pero 0 facturas distintas válidas
        assert d["total_glosas"] == 2
        assert d["facturas_distintas"] == 0
