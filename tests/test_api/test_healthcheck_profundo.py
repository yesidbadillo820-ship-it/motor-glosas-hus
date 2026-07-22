"""Tests del endpoint /sistema/healthcheck-profundo (R70 P2)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthcheck_profundo_publico_sin_auth():
    """Endpoint público para monitores externos."""
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/sistema/healthcheck-profundo")
        assert r.status_code in (200, 503)


def test_estructura_respuesta():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/sistema/healthcheck-profundo")
        d = r.json()
        assert "estado" in d
        assert "componentes" in d
        assert "ahora" in d
        assert d["estado"] in ("ok", "degraded", "down")


def test_componentes_incluyen_bd():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/sistema/healthcheck-profundo")
        d = r.json()
        assert "bd" in d["componentes"]
        # BD debe responder OK con SQLite in-memory
        assert d["componentes"]["bd"]["ok"] is True
        assert "latency_ms" in d["componentes"]["bd"]


def test_componentes_incluyen_schedulers():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/sistema/healthcheck-profundo")
        d = r.json()
        assert "scheduler_pre_analisis" in d["componentes"]
        assert "scheduler_mantenimiento" in d["componentes"]


def test_status_code_503_si_degradado():
    """Si la BD falla → 503. Ronda 30: antes el test NUNCA ejercitaba la
    rama 503 (solo consultaba el caso OK y replicaba la lógica en un
    comentario). Ahora se mockea el fallo de db.execute y se verifica que
    el endpoint devuelve realmente 503 con bd.ok=False."""
    from app.database import get_db
    from app.main import app

    class _DbRota:
        def execute(self, *a, **k):
            raise RuntimeError("BD caída (simulada)")

        def __getattr__(self, _n):
            def _noop(*a, **k):
                return None

            return _noop

    app.dependency_overrides[get_db] = lambda: iter([_DbRota()]).__next__()
    try:
        with TestClient(app) as c:
            r = c.get("/sistema/healthcheck-profundo")
        assert r.status_code == 503
        d = r.json()
        assert d["componentes"]["bd"]["ok"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_status_code_200_si_ok():
    """Complemento: el caso OK sigue devolviendo 200 (documentación viva)."""
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/sistema/healthcheck-profundo")
        d = r.json()
        # Si todos OK, status 200; si alguno KO, 503.
        if d["estado"] == "ok":
            assert r.status_code == 200
        else:
            assert r.status_code == 503
