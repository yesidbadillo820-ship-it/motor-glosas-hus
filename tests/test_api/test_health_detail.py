"""Tests del endpoint GET /health/detail y del X-Request-ID middleware."""

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
    s.add(UsuarioRecord(id=1, email="admin@hus.gov.co", rol="SUPER_ADMIN", activo=1))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def usuario_admin():
    return UsuarioRecord(id=1, email="admin@hus.gov.co", rol="SUPER_ADMIN", activo=1)


@pytest.fixture
def client(db_session, usuario_admin):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealthPublico:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_health_no_requiere_auth(self, client):
        from app.api.deps import get_usuario_actual
        from app.main import app

        overrides_backup = dict(app.dependency_overrides)
        app.dependency_overrides.pop(get_usuario_actual, None)
        try:
            r = client.get("/health")
            assert r.status_code == 200
        finally:
            app.dependency_overrides.update(overrides_backup)


class TestHealthDetail:
    def test_estructura_basica(self, client):
        r = client.get("/health/detail")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "timestamp" in body
        assert "uptime" in body
        assert "uptime_seconds" in body
        assert "python" in body
        assert "database" in body
        assert "system" in body
        assert "ai" in body

    def test_database_stats(self, client):
        r = client.get("/health/detail")
        db = r.json()["database"]
        assert "total_glosas" in db
        assert "total_usuarios" in db
        assert db["total_glosas"] >= 0

    def test_ai_config_flags(self, client):
        r = client.get("/health/detail")
        ai = r.json()["ai"]
        assert "primary" in ai
        assert "anthropic_configured" in ai
        assert isinstance(ai["anthropic_configured"], bool)

    def test_uptime_positivo(self, client):
        r = client.get("/health/detail")
        assert r.json()["uptime_seconds"] >= 0


class TestCorrelationIdMiddleware:
    def test_respuesta_incluye_request_id(self, client):
        r = client.get("/health")
        assert "x-request-id" in r.headers

    def test_request_id_es_uuid_cuando_no_enviado(self, client):
        import re

        r = client.get("/health")
        rid = r.headers.get("x-request-id", "")
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            rid,
        ), f"No es UUID4: {rid!r}"

    def test_request_id_enviado_es_devuelto(self, client):
        custom_id = "mi-trace-123"
        r = client.get("/health", headers={"X-Request-ID": custom_id})
        assert r.headers.get("x-request-id") == custom_id

    def test_distintos_requests_distintos_ids(self, client):
        ids = {client.get("/health").headers["x-request-id"] for _ in range(3)}
        assert len(ids) == 3
