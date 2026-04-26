"""Tests del endpoint GET /sistema/runtime-info (R107 P2)."""
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


class TestRuntimeInfo:
    def test_estructura_basica(self, client):
        r = client.get("/sistema/runtime-info")
        assert r.status_code == 200, r.text
        d = r.json()
        # Estos campos siempre deben estar (sin depender de psutil)
        for key in ("python_version", "python_implementation", "platform",
                    "machine", "pid", "cwd", "threads_activos",
                    "psutil_disponible"):
            assert key in d

    def test_python_version_formato(self, client):
        r = client.get("/sistema/runtime-info")
        d = r.json()
        # Formato X.Y.Z
        partes = d["python_version"].split(".")
        assert len(partes) >= 2
        assert partes[0].isdigit()

    def test_pid_es_entero(self, client):
        r = client.get("/sistema/runtime-info")
        d = r.json()
        assert isinstance(d["pid"], int)
        assert d["pid"] > 0

    def test_threads_positivo(self, client):
        r = client.get("/sistema/runtime-info")
        d = r.json()
        assert d["threads_activos"] >= 1
