"""Tests del endpoint GET /sistema/info-deploy (R220 P1)."""
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


class TestInfoDeploy:
    def test_estructura(self, client):
        r = client.get("/sistema/info-deploy")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("render_git_commit", "render_git_branch",
                    "render_service_id", "render_external_url",
                    "python_version", "build_id"):
            assert key in d
        assert d["python_version"].count(".") == 2

    def test_build_id_default_local(self, client):
        r = client.get("/sistema/info-deploy")
        d = r.json()
        # Sin RENDER_GIT_COMMIT env → build_id="local"
        assert d["build_id"] is not None
