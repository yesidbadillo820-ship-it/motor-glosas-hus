"""Tests del endpoint GET /contratos/exportar.csv (R163 P1)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ContratoRecord, UsuarioRecord


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


class TestContratosCSV:
    def test_csv_content_type(self, client):
        r = client.get("/contratos/exportar.csv")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

    def test_header_row(self, client):
        r = client.get("/contratos/exportar.csv")
        primera = r.text.split("\n")[0]
        assert "eps" in primera
        assert "detalles" in primera

    def test_filas_correctas(self, client, db_session):
        db_session.add(ContratoRecord(eps="ZETA", detalles="info1"))
        db_session.add(ContratoRecord(eps="ALPHA", detalles="info2"))
        db_session.commit()

        r = client.get("/contratos/exportar.csv")
        lineas = [l for l in r.text.strip().split("\n") if l]
        # 1 header + 2 contratos
        assert len(lineas) == 3
        # Orden alfabético
        assert lineas[1].startswith("ALPHA")
        assert lineas[2].startswith("ZETA")
