"""Tests del endpoint GET /sistema/banner-info (R143 P2)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


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
def usuario_coord():
    return UsuarioRecord(
        id=1, email="coord@hus.gov.co", rol="COORDINADOR", activo=1,
    )


@pytest.fixture
def client(db_session, usuario_coord):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario_coord
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestBannerInfo:
    def test_estructura(self, client):
        r = client.get("/sistema/banner-info")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("mostrar_banner", "mensaje",
                    "modo_capacitacion", "tipo"):
            assert key in d
        assert d["tipo"] == "info"

    def test_sin_banner_default(self, client):
        # Sin BANNER_CAPACITACION env → mensaje vacío
        r = client.get("/sistema/banner-info")
        d = r.json()
        # Por defecto la config tiene banner_capacitacion=""
        assert d["mostrar_banner"] is False
        assert d["mensaje"] is None
        assert d["modo_capacitacion"] is False

    def test_consistencia_flags(self, client):
        r = client.get("/sistema/banner-info")
        d = r.json()
        # mostrar_banner y modo_capacitacion deben coincidir
        assert d["mostrar_banner"] == d["modo_capacitacion"]
