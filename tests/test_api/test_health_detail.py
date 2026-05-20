"""Tests del endpoint GET /health/detail y del X-Request-ID middleware."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import AICallRecord, UsuarioRecord


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


class TestMiDiaDashboard:
    def test_estructura_basica(self, client):
        r = client.get("/mi-dia")
        assert r.status_code == 200
        body = r.json()
        assert "fecha" in body
        assert "saludo" in body
        assert "tareas" in body
        assert "glosas" in body
        assert "alertas" in body

    def test_tareas_tienen_campos(self, client):
        r = client.get("/mi-dia")
        tareas = r.json()["tareas"]
        assert "pendientes" in tareas
        assert "completadas" in tareas
        assert "total" in tareas
        assert tareas["total"] == tareas["pendientes"] + tareas["completadas"]

    def test_glosas_tienen_campos(self, client):
        r = client.get("/mi-dia")
        glosas = r.json()["glosas"]
        assert "asignadas_activas" in glosas
        assert "vencen_48h" in glosas
        assert "sin_dictamen" in glosas

    def test_alertas_nivel_valido(self, client):
        r = client.get("/mi-dia")
        nivel = r.json()["alertas"]["nivel"]
        assert nivel in ("OK", "MEDIA", "ALTA")

    def test_saludo_no_vacio(self, client):
        r = client.get("/mi-dia")
        assert len(r.json()["saludo"]) > 0


class TestDiagnosticoIA:
    def test_sin_llamadas_devuelve_estado_sin_datos(self, client):
        r = client.get("/sistema/diagnostico-ia")
        assert r.status_code == 200
        body = r.json()
        assert body["total_calls"] == 0
        assert body["estado"] == "SIN_DATOS"
        assert body["proveedores"] == {}

    def test_con_llamadas_agrega_por_proveedor(self, client, db_session):
        from datetime import datetime, timezone

        ahora = datetime.now(timezone.utc)
        # 3 calls de Groq con distintas latencias y éxito
        db_session.add_all(
            [
                AICallRecord(
                    proveedor="groq",
                    modelo="llama-3.3-70b",
                    latency_ms=1200,
                    output_tokens=500,
                    creado_en=ahora,
                ),
                AICallRecord(
                    proveedor="groq",
                    modelo="llama-3.3-70b",
                    latency_ms=800,
                    output_tokens=300,
                    creado_en=ahora,
                ),
                AICallRecord(
                    proveedor="groq",
                    modelo="llama-3.3-70b",
                    latency_ms=3500,
                    output_tokens=0,  # fallo
                    creado_en=ahora,
                ),
                AICallRecord(
                    proveedor="anthropic",
                    modelo="claude-sonnet-4-6",
                    latency_ms=5000,
                    output_tokens=900,
                    cost_usd=0.045,
                    creado_en=ahora,
                ),
            ]
        )
        db_session.commit()

        r = client.get("/sistema/diagnostico-ia?horas=24")
        assert r.status_code == 200
        body = r.json()
        assert body["total_calls"] == 4
        assert "groq" in body["proveedores"]
        assert "anthropic" in body["proveedores"]
        groq = body["proveedores"]["groq"]
        assert groq["total_calls"] == 3
        assert groq["tasa_exito_pct"] == round(100 * 2 / 3, 1)
        assert groq["latency_ms"]["p50"] >= 800
        anth = body["proveedores"]["anthropic"]
        assert anth["total_calls"] == 1
        assert anth["costo_usd"] == 0.045

    def test_clampa_horas_a_rango_valido(self, client):
        # 0 → mínimo 1, 999 → máximo 168
        r1 = client.get("/sistema/diagnostico-ia?horas=0")
        assert r1.status_code == 200
        assert r1.json()["ventana_horas"] == 1
        r2 = client.get("/sistema/diagnostico-ia?horas=999")
        assert r2.status_code == 200
        assert r2.json()["ventana_horas"] == 168


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
