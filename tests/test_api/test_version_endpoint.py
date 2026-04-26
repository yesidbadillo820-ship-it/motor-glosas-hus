"""Tests del endpoint público GET /sistema/version (R64 P1)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_version_endpoint_publico_sin_auth():
    """El endpoint debe ser público (sin requerir Bearer token).
    Caso de uso: frontend lo consulta sin estar logueado para
    decidir si forzar reload por nuevo deploy."""
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/sistema/version")
        assert r.status_code == 200
        d = r.json()
        # Campos obligatorios
        assert "version" in d
        assert "commit" in d
        assert "commit_full" in d
        assert "build_time" in d
        assert "python" in d
        assert "env" in d


def test_version_no_expone_secretos():
    """SECURITY: el endpoint público NO debe revelar API keys, env vars
    sensibles, paths del filesystem, ni nada que ayude a un atacante."""
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/sistema/version")
        d = r.json()
        # Convertir todo a string para grep
        body = str(d).lower()
        # Patrones prohibidos
        for forbidden in (
            "api_key", "secret", "password", "token",
            "/home/", "/opt/", "anthropic", "groq",
            "sentry_dsn", "smtp",
        ):
            assert forbidden not in body, (
                f"REGRESIÓN crítica: /sistema/version expone '{forbidden}'"
            )


def test_version_commit_short_es_7_chars():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/sistema/version")
        d = r.json()
        # commit puede ser 'dev' o 7 chars hex
        assert len(d["commit"]) <= 7


def test_version_python_es_string_corto():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/sistema/version")
        d = r.json()
        # Solo "3.11.15" no la versión completa con compilador
        assert len(d["python"]) <= 10
        assert "." in d["python"]


def test_version_env_var_propagated(monkeypatch):
    """Si se setea RENDER_GIT_COMMIT, debe aparecer en la respuesta."""
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc1234567890def")
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/sistema/version")
        d = r.json()
        assert d["commit"] == "abc1234"
        assert d["commit_full"] == "abc1234567890def"
