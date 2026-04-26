"""Tests del endpoint GET /contratos/sin-glosas (R132 P1)."""
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


def _seed_contrato(db, eps, detalles="X"):
    db.add(ContratoRecord(eps=eps, detalles=detalles))
    db.commit()


def _seed_glosa(db, eps):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa="C",
        valor_objetado=1000, etapa="X", estado="RADICADA",
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestContratosSinGlosas:
    def test_estructura(self, client):
        r = client.get("/contratos/sin-glosas")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_contratos", "contratos_con_glosas",
                    "contratos_sin_glosas", "items"):
            assert key in d

    def test_sin_contratos(self, client):
        r = client.get("/contratos/sin-glosas")
        d = r.json()
        assert d["total_contratos"] == 0
        assert d["items"] == []

    def test_detecta_contratos_sin_glosas(self, client, db_session):
        _seed_contrato(db_session, "SANITAS")
        _seed_contrato(db_session, "INACTIVA")
        _seed_glosa(db_session, "SANITAS")  # solo SANITAS tiene glosas

        r = client.get("/contratos/sin-glosas")
        d = r.json()
        assert d["total_contratos"] == 2
        assert d["contratos_con_glosas"] == 1
        assert d["contratos_sin_glosas"] == 1
        eps_inactivas = [it["eps"] for it in d["items"]]
        assert eps_inactivas == ["INACTIVA"]

    def test_orden_alfabetico(self, client, db_session):
        _seed_contrato(db_session, "ZETA")
        _seed_contrato(db_session, "ALPHA")
        _seed_contrato(db_session, "MIDDLE")
        # Ninguna tiene glosas
        r = client.get("/contratos/sin-glosas")
        d = r.json()
        eps = [it["eps"] for it in d["items"]]
        assert eps == ["ALPHA", "MIDDLE", "ZETA"]
