"""El diagnóstico no muestra avisos que el auditor no puede resolver.

19-08-2026. Yesid pidió activar Sentry —el buzón de errores—, intentó crear la
cuenta y se topó con que sentry.io le exige entrar por **Fly.io**: su correo
quedó amarrado a ese inicio de sesión. No puede activarlo. Su respuesta fue
«quitar eso mejor».

Tenía razón, y es la misma lección del ticker de noticias: **un aviso ámbar que
aparece día tras día y que nadie puede resolver enseña a ignorar los avisos
ámbar**. Cuando aparezca uno de verdad, ya nadie lo mira.

Pasaba con dos:

  · **Sentry** — «los errores en producción se pierden silenciosamente».
  · **PostHog** — «no estamos midiendo qué gestores usan qué features».

Los dos, además, daban instrucciones de un servidor Linux con Docker
(`sudo nano /opt/motor-glosas/.env`) cuando el motor corre en Windows.

Ahora solo se reportan **si están configurados**, para confirmar que quedaron
funcionando. La integración sigue montada: basta poner la variable en el `.env`
para que se active y vuelva a aparecer, en verde.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _diagnostico(monkeypatch, **entorno) -> dict:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_admin
    from app.api.routers.diagnostico import router
    from app.database import get_db
    from app.models.db import UsuarioRecord

    for clave in ("SENTRY_DSN", "POSTHOG_API_KEY"):
        monkeypatch.delenv(clave, raising=False)
    for clave, valor in entorno.items():
        monkeypatch.setenv(clave, valor)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_admin] = lambda: UsuarioRecord(
        id=1, email="a@b.c", rol="SUPER_ADMIN", activo=1
    )

    class _Db:
        def query(self, *a, **k):
            raise RuntimeError("sin base en esta prueba")

    app.dependency_overrides[get_db] = lambda: _Db()
    with TestClient(app) as c:
        r = c.get("/admin/diagnostico")
    assert r.status_code == 200, r.text
    return r.json()


class TestSinConfigurar:
    def test_sentry_no_aparece(self, monkeypatch):
        secciones = _diagnostico(monkeypatch)["secciones"]
        assert "sentry" not in secciones, "volvió el aviso que el auditor no puede resolver"

    def test_posthog_no_aparece(self, monkeypatch):
        assert "posthog" not in _diagnostico(monkeypatch)["secciones"]

    def test_el_resto_del_diagnostico_sigue_reportando(self, monkeypatch):
        """Se callaron dos avisos, no la pantalla entera."""
        secciones = _diagnostico(monkeypatch)["secciones"]
        assert len(secciones) >= 3, list(secciones)


class TestConfigurado:
    def test_sentry_si_se_reporta_cuando_esta_puesto(self, monkeypatch):
        secciones = _diagnostico(monkeypatch, SENTRY_DSN="https://abc123@o1.ingest.sentry.io/2")[
            "secciones"
        ]
        assert "sentry" in secciones, "si se configura, hay que confirmar que quedó activo"

    def test_posthog_si_se_reporta_cuando_esta_puesto(self, monkeypatch):
        secciones = _diagnostico(monkeypatch, POSTHOG_API_KEY="phc_prueba")["secciones"]
        assert "posthog" in secciones


class TestNingunAvisoManaAOtroSistema:
    """Ningún mensaje del diagnóstico puede mandar al auditor a correr
    comandos de Linux: el motor vive en el PC de cartera, en Windows."""

    @pytest.mark.parametrize(
        "comando", ["sudo nano", "docker compose", "/opt/motor-glosas", "sudo docker"]
    )
    def test_no_hay_instrucciones_de_linux(self, comando):
        fuente = (RAIZ / "app" / "api" / "routers" / "diagnostico.py").read_text(encoding="utf-8")
        # Se permite nombrarlo en un comentario que explique por qué se quitó.
        lineas_vivas = [
            ln for ln in fuente.splitlines() if comando in ln and not ln.strip().startswith("#")
        ]
        assert not lineas_vivas, f"el diagnóstico manda a correr «{comando}»: {lineas_vivas}"
