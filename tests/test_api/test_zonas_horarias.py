"""Tests del endpoint GET /sistema/zonas-horarias (R101 P1)."""
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


class TestZonasHorarias:
    def test_estructura(self, client):
        r = client.get("/sistema/zonas-horarias")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("now_utc", "now_local", "now_local_tz_aware",
                    "server_tz_env", "python_tz_module",
                    "bogota_offset_utc"):
            assert key in d

    def test_now_utc_iso(self, client):
        r = client.get("/sistema/zonas-horarias")
        d = r.json()
        # Debe ser ISO string parseable
        from datetime import datetime
        # Espera formato ISO con offset
        assert "T" in d["now_utc"]
        # +00:00 indica UTC
        assert d["now_utc"].endswith("+00:00") or "Z" in d["now_utc"]

    def test_python_tz_module_known(self, client):
        r = client.get("/sistema/zonas-horarias")
        d = r.json()
        assert d["python_tz_module"] in ("zoneinfo", "pytz", "ninguno")

    def test_bogota_offset_si_zoneinfo(self, client):
        r = client.get("/sistema/zonas-horarias")
        d = r.json()
        if d["python_tz_module"] == "zoneinfo":
            # Bogotá es UTC-5 sin DST
            assert d["bogota_offset_utc"] == -5.0
