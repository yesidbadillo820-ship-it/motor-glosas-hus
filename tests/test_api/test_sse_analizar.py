"""Tests del endpoint SSE GET /eventos/analizar/{trace_id}."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord


@pytest.fixture(autouse=True)
def _limpiar_colas():
    from app.services.progreso_analisis import _COLAS

    _COLAS.clear()
    yield
    _COLAS.clear()


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
def client(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    admin = UsuarioRecord(id=1, email="admin@hus.gov.co", rol="SUPER_ADMIN", activo=1)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_usuario_actual] = lambda: admin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestSSEAnalizar:
    def test_recibe_evento_finalizado_y_cierra(self, client):
        # Publicar 'finalizado' antes de abrir el stream → debe llegar y cerrar
        from app.services.progreso_analisis import obtener_cola, publicar

        # Pre-cargar la cola con un evento finalizado
        obtener_cola("trace-X")
        publicar("trace-X", "inicio", {"eps": "TEST"})
        publicar("trace-X", "finalizado", {"ok": True})

        with client.stream("GET", "/eventos/analizar/trace-X") as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            # Recolectar todo el stream (debe cerrarse rápido tras 'finalizado')
            body = b"".join(r.iter_bytes()).decode("utf-8")
        assert "event: inicio" in body
        assert "event: finalizado" in body
        # data: {"ok": true} debe estar
        assert '"ok"' in body

    def test_cola_se_limpia_al_finalizar(self, client):
        from app.services.progreso_analisis import _COLAS, obtener_cola, publicar

        obtener_cola("trace-cleanup")
        publicar("trace-cleanup", "finalizado", {"ok": True})

        with client.stream("GET", "/eventos/analizar/trace-cleanup") as r:
            b"".join(r.iter_bytes())  # drenar

        assert "trace-cleanup" not in _COLAS
