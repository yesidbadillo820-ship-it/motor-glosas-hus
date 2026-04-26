"""Tests del endpoint GET /notificaciones/contadores (R158 P1)."""
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


class TestNotificacionesContadores:
    def test_estructura(self, client):
        r = client.get("/notificaciones/contadores")
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("total", "por_tipo", "generado_en"):
            assert key in d
        assert isinstance(d["por_tipo"], dict)

    def test_total_es_int(self, client):
        r = client.get("/notificaciones/contadores")
        d = r.json()
        assert isinstance(d["total"], int)
