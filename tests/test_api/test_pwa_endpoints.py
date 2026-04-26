"""Tests del PWA router (R79 P1).

Cubre los endpoints estáticos del shell de la app (icons, manifest,
service worker, reset-sw). No requieren auth — todos públicos por
diseño.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_devuelve_html():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/")
        # 200 o 404 según existencia del archivo, pero NO 500
        assert r.status_code in (200, 404)


def test_manifest_es_publico():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/manifest.webmanifest")
        # 200 o 404 según existencia
        assert r.status_code in (200, 404)


def test_sw_js_no_store_headers():
    """REGRESIÓN R51 P6: el service worker DEBE servirse con no-store
    para que cambios en el SW lleguen tras un deploy."""
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/sw.js")
        if r.status_code == 200:
            cc = r.headers.get("cache-control", "")
            assert "no-store" in cc.lower() or "no-cache" in cc.lower()


def test_icon_192_devuelve_png():
    """Genera icono PWA dinámicamente con Pillow."""
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/icon-192.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        # PNG tiene signature 8 bytes \x89PNG\r\n\x1a\n
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_icon_512_devuelve_png():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/icon-512.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"


def test_reset_sw_devuelve_html_con_script():
    """La página de emergencia debe traer el JavaScript que limpia
    service workers + caches del navegador."""
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/reset-sw.html")
        assert r.status_code == 200
        body = r.text
        assert "serviceWorker" in body
        assert "caches" in body
        assert "unregister" in body


def test_endpoints_sin_auth_son_publicos():
    """Confirma que los endpoints PWA NO requieren Bearer token."""
    from app.main import app
    publicos = [
        "/manifest.webmanifest",
        "/sw.js",
        "/icon-192.png",
        "/icon-512.png",
        "/reset-sw.html",
    ]
    with TestClient(app) as c:
        for path in publicos:
            r = c.get(path)
            # Cualquiera de 200 (file existe) o 404 (file no), NUNCA 401
            assert r.status_code != 401, (
                f"REGRESIÓN: {path} requiere auth pero debería ser público"
            )
