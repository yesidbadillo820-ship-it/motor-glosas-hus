"""El panel no invita a reiniciar un indexado que va a la mitad — 19-08-2026.

Con el servidor real (`\\\\Prime\\radicacion_2026`) el indexador reportó:

    "facturas_indexadas": 44671,
    "archivos_escaneados": 432314,
    "construido_en_epoch": 0,      ← nunca ha terminado una build
    "construyendo": true           ← está trabajando AHORA

…y el panel de Diagnóstico decía:

    ⚠ «44671 facturas indexadas pero la última build es vieja (>24h)»

No era vieja: **no existía**, porque la primera revisión completa de 432.314
archivos por red todavía iba corriendo. Y ese mensaje invita a apretar
«Reindexar soportes», que lo haría **empezar de cero un trabajo de horas**.

Son tres situaciones distintas y el panel las daba todas por la misma:
  · está indexando ahora  → hay que esperar, y NO tocar el botón;
  · nunca terminó una     → hay que arrancarla;
  · terminó hace >24h     → puede faltar lo radicado desde entonces.
"""

from __future__ import annotations

import pytest


def _seccion(monkeypatch, stats: dict) -> dict:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.deps import get_admin
    from app.api.routers.diagnostico import router
    from app.database import get_db
    from app.models.db import UsuarioRecord
    from app.services import soportes_autodiscovery_service as svc

    class _Idx:
        def stats(self):
            return stats

    monkeypatch.setattr(svc, "get_indexer", lambda: _Idx())

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_admin] = lambda: UsuarioRecord(
        id=1, email="a@b.c", rol="SUPER_ADMIN", activo=1
    )

    class _Db:
        def query(self, *a, **k):
            raise RuntimeError("sin base")

    app.dependency_overrides[get_db] = lambda: _Db()
    with TestClient(app) as c:
        r = c.get("/admin/diagnostico")
    assert r.status_code == 200, r.text
    return r.json()["secciones"].get("soportes_indexer", {})


# Lo que reportó el servidor real de Yesid.
REAL = {
    "raiz": "\\\\Prime\\radicacion_2026\\",
    "raiz_existe": True,
    "facturas_indexadas": 44671,
    "archivos_escaneados": 432314,
    "archivos_indexados": 403904,
    "construido_en_epoch": 0,
    "construido_hace_seg": None,
    "construyendo": True,
    "ultimo_error": None,
}


class TestMientrasIndexa:
    def test_no_dice_que_la_build_es_vieja(self, monkeypatch):
        assert "vieja" not in _seccion(monkeypatch, REAL)["mensaje"]

    def test_dice_que_esta_trabajando_y_cuanto_lleva(self, monkeypatch):
        m = _seccion(monkeypatch, REAL)["mensaje"]
        assert "Indexando" in m
        assert "44671" in m

    def test_avisa_expresamente_de_no_reiniciarlo(self, monkeypatch):
        """Es el daño concreto: reiniciar tira horas de trabajo a la basura."""
        m = _seccion(monkeypatch, REAL)["mensaje"]
        assert "NO le dé «Reindexar soportes»" in m
        assert "empezar de nuevo" in m

    def test_no_pinta_alarma_por_estar_trabajando(self, monkeypatch):
        assert _seccion(monkeypatch, REAL)["estado"] == "ok"

    def test_advierte_que_puede_faltar_una_factura_reciente(self, monkeypatch):
        assert "todavía no aparezca" in _seccion(monkeypatch, REAL)["mensaje"]


class TestLasOtrasDosSituaciones:
    def test_nunca_termino_una_revision(self, monkeypatch):
        stats = {**REAL, "construyendo": False}
        s = _seccion(monkeypatch, stats)
        assert s["estado"] == "warning"
        assert "no ha terminado ninguna revisión completa" in s["mensaje"]

    def test_la_ultima_fue_hace_mas_de_un_dia(self, monkeypatch):
        stats = {**REAL, "construyendo": False, "construido_hace_seg": 30 * 3600}
        s = _seccion(monkeypatch, stats)
        assert s["estado"] == "warning"
        assert "más de un día" in s["mensaje"]
        assert "pueden no aparecer" in s["mensaje"]

    def test_al_dia_queda_en_verde(self, monkeypatch):
        stats = {**REAL, "construyendo": False, "construido_hace_seg": 3600}
        s = _seccion(monkeypatch, stats)
        assert s["estado"] == "ok"
        assert "build hace 1.0h" in s["mensaje"]


class TestSinIndice:
    def test_indice_vacio_explica_donde_se_configura(self, monkeypatch):
        stats = {**REAL, "facturas_indexadas": 0, "construyendo": False}
        m = _seccion(monkeypatch, stats)["mensaje"]
        assert "soportes_root.txt" in m

    @pytest.mark.parametrize("comando", ["sudo nano", "docker compose"])
    def test_ningun_mensaje_manda_a_un_servidor_linux(self, monkeypatch, comando):
        for stats in (
            REAL,
            {**REAL, "construyendo": False},
            {**REAL, "construyendo": False, "construido_hace_seg": 30 * 3600},
            {**REAL, "facturas_indexadas": 0, "construyendo": False},
        ):
            assert comando not in _seccion(monkeypatch, stats).get("mensaje", "")
