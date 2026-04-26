"""Tests del endpoint GET /contratos/eps-sin-contrato (R132 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ContratoRecord, GlosaRecord, UsuarioRecord


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


def _seed_contrato(db, eps):
    db.add(ContratoRecord(eps=eps, detalles="X"))
    db.commit()


def _seed_glosa(db, eps, valor=1000):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=valor, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestEpsSinContrato:
    def test_estructura(self, client):
        r = client.get("/contratos/eps-sin-contrato")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_eps_sin_contrato", "items"):
            assert key in d

    def test_eps_con_contrato_no_aparece(self, client, db_session):
        _seed_contrato(db_session, "SANITAS")
        _seed_glosa(db_session, "SANITAS")
        r = client.get("/contratos/eps-sin-contrato")
        d = r.json()
        assert d["items"] == []

    def test_detecta_eps_sin_contrato(self, client, db_session):
        _seed_contrato(db_session, "SANITAS")
        _seed_glosa(db_session, "EPS_NO_CONTRATADA", valor=5000)
        _seed_glosa(db_session, "SANITAS", valor=1000)

        r = client.get("/contratos/eps-sin-contrato")
        d = r.json()
        assert d["total_eps_sin_contrato"] == 1
        item = d["items"][0]
        assert item["eps"] == "EPS_NO_CONTRATADA"
        assert item["glosas_acumuladas"] == 1
        assert item["valor_objetado_total"] == 5000

    def test_orden_por_valor_desc(self, client, db_session):
        # Sin contratos: ambas son "sin contrato"
        _seed_glosa(db_session, "EPS_GRANDE", valor=10_000_000)
        _seed_glosa(db_session, "EPS_PEQUENA", valor=1_000)

        r = client.get("/contratos/eps-sin-contrato")
        d = r.json()
        assert d["items"][0]["eps"] == "EPS_GRANDE"
        assert d["items"][1]["eps"] == "EPS_PEQUENA"
