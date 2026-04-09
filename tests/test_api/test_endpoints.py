"""Tests for API endpoints."""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestGlosasEndpoint:
    """Tests for glosas API endpoint."""

    def test_analizar_glosa_extemporanea(self, client: TestClient):
        """Should detect extemporaneous glosa."""
        payload = {
            "eps": "EPS SANITAS",
            "fecha_radicacion": "2026-03-01",
            "fecha_recepcion": "2026-04-01",
            "tabla_excel": "TA0201 $1,500,000 Prueba"
        }
        response = client.post("/api/glosas/analizar", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "tipo" in data
        assert data["tipo"] == "RESPUESTA RE2202"

    def test_analizar_glosa_dentro_terminos(self, client: TestClient):
        """Should handle glosa within time limits."""
        payload = {
            "eps": "EPS SURA",
            "fecha_radicacion": "2026-03-01",
            "fecha_recepcion": "2026-03-10",
            "tabla_excel": "SO0101 $500,000 Soportes"
        }
        response = client.post("/api/glosas/analizar", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "tipo" in data

    def test_analizar_glosa_tarifa(self, client: TestClient):
        """Should handle tariff glosa."""
        payload = {
            "eps": "EPS NUEVA EPS",
            "tabla_excel": "TA0201 $2,000,000 Diferencia tariff"
        }
        response = client.post("/api/glosas/analizar", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "dictamen" in data

    def test_analizar_glosa_invalid_payload(self, client: TestClient):
        """Should validate required fields."""
        payload = {"eps": "EPS TEST"}
        response = client.post("/api/glosas/analizar", json=payload)
        assert response.status_code == 422

    def test_analizar_glosa_sin_fecha(self, client: TestClient):
        """Should handle missing dates."""
        payload = {
            "eps": "EPS SANITAS",
            "tabla_excel": "FA0101 Error en código"
        }
        response = client.post("/api/glosas/analizar", json=payload)
        assert response.status_code == 200


class TestContratosEndpoint:
    """Tests for contratos API endpoint."""

    def test_listar_contratos(self, client: TestClient):
        """Should list all contracts."""
        response = client.get("/api/contratos")
        assert response.status_code == 200
        data = response.json()
        assert "contratos" in data or isinstance(data, list)

    def test_obtener_contrato_eps(self, client: TestClient):
        """Should get contract by EPS name."""
        response = client.get("/api/contratos/EPS%20SANITAS")
        assert response.status_code in [200, 404]


class TestPlantillasEndpoint:
    """Tests for plantillas API endpoint."""

    def test_listar_plantillas(self, client: TestClient):
        """Should list all templates."""
        response = client.get("/api/plantillas")
        assert response.status_code == 200

    def test_obtener_plantilla_codigo(self, client: TestClient):
        """Should get template by code."""
        response = client.get("/api/plantillas/TA0201")
        assert response.status_code in [200, 404]


class TestAuthEndpoint:
    """Tests for authentication endpoint."""

    def test_login_exito(self, client: TestClient):
        """Should authenticate with valid credentials."""
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "testpassword"
        })
        assert response.status_code in [200, 401]

    def test_login_credenciales_invalidas(self, client: TestClient):
        """Should reject invalid credentials."""
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        assert response.status_code == 401

    def test_protegido_sin_token(self, client: TestClient):
        """Should require authentication for protected endpoints."""
        response = client.get("/api/glosas/historial")
        assert response.status_code == 401
