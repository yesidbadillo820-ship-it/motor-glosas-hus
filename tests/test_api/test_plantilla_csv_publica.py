"""Test: GET /glosas/importar-masiva/plantilla.csv es público (sin auth)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db


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
def client_sin_auth(db_session):
    """Cliente SIN override de get_usuario_actual — simula request anónima."""
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_plantilla_csv_publica(client_sin_auth):
    """El endpoint de plantilla CSV no requiere token (frontend usa <a href>)."""
    r = client_sin_auth.get("/glosas/importar-masiva/plantilla.csv")
    assert r.status_code == 200
    body = r.text
    assert "ENTIDAD" in body
    assert "FACTURA" in body
    assert "FAMISANAR" in body  # fila de ejemplo


def test_plantilla_csv_devuelve_tsv_con_disposition(client_sin_auth):
    r = client_sin_auth.get("/glosas/importar-masiva/plantilla.csv")
    assert r.headers["content-type"].startswith("text/tab-separated-values")
    assert "attachment" in r.headers["content-disposition"]
    assert "plantilla-importacion-masiva.tsv" in r.headers["content-disposition"]
