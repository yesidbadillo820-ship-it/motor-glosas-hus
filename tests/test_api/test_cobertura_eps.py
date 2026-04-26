"""Tests del endpoint GET /tarifas-contratadas/cobertura-eps (R168 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import TarifaContratadaRecord, UsuarioRecord


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


def _seed(db, eps, codigo="C", contrato="CT-1"):
    db.add(TarifaContratadaRecord(
        eps=eps, codigo_cups=codigo,
        contrato_numero=contrato, valor_pactado=1000,
    ))
    db.commit()


class TestCoberturaEPS:
    def test_estructura(self, client):
        r = client.get("/tarifas-contratadas/cobertura-eps")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total_eps_con_tarifas",
                    "total_tarifas_cargadas", "items"):
            assert key in d

    def test_orden_count_desc(self, client, db_session):
        for i in range(5):
            _seed(db_session, "GRANDE", codigo=f"C{i}")
        for i in range(2):
            _seed(db_session, "PEQUENA", codigo=f"D{i}")
        r = client.get("/tarifas-contratadas/cobertura-eps")
        d = r.json()
        assert d["items"][0]["eps"] == "GRANDE"
        assert d["items"][0]["tarifas_count"] == 5
        assert d["items"][1]["eps"] == "PEQUENA"

    def test_contratos_distintos(self, client, db_session):
        _seed(db_session, "X", codigo="C1", contrato="CT-A")
        _seed(db_session, "X", codigo="C2", contrato="CT-A")
        _seed(db_session, "X", codigo="C3", contrato="CT-B")

        r = client.get("/tarifas-contratadas/cobertura-eps")
        d = r.json()
        assert d["items"][0]["contratos_distintos"] == 2
