"""Tests for API endpoints.

Most endpoints require authentication. These tests verify that the routes
exist (not 404) and correctly enforce authentication (401 without token).
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Should return ok status and version."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestGlosasEndpoint:
    """Tests for glosas API endpoints."""

    def test_analizar_requiere_autenticacion(self, client: TestClient):
        """POST /analizar should require a bearer token."""
        response = client.post("/analizar", data={})
        assert response.status_code == 401

    def test_historial_requiere_autenticacion(self, client: TestClient):
        """GET /glosas/historial should require a bearer token."""
        response = client.get("/glosas/historial")
        assert response.status_code == 401

    def test_alertas_requiere_autenticacion(self, client: TestClient):
        """GET /glosas/alertas should require a bearer token."""
        response = client.get("/glosas/alertas")
        assert response.status_code == 401


class TestContratosEndpoint:
    """Tests for contratos API endpoint."""

    def test_listar_contratos_requiere_autenticacion(self, client: TestClient):
        """GET /contratos/ should require a bearer token."""
        response = client.get("/contratos/")
        assert response.status_code == 401


class TestPlantillasEndpoint:
    """Tests for plantillas API endpoint."""

    def test_listar_plantillas_requiere_autenticacion(self, client: TestClient):
        """GET /plantillas/ should require a bearer token."""
        response = client.get("/plantillas/")
        assert response.status_code == 401


class TestAuthEndpoint:
    """Tests for authentication endpoint."""

    def test_login_credenciales_invalidas(self, client: TestClient):
        """Invalid credentials should be rejected with 401."""
        response = client.post(
            "/token",
            data={"username": "no-existe@hus.gov.co", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    def test_login_requiere_form_data(self, client: TestClient):
        """Missing form data should return 422."""
        response = client.post("/token", json={})
        assert response.status_code == 422
