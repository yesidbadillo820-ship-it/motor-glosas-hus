"""Ninguna pantalla puede llamar a una ruta que no existe.

OT-039 · 13-08-2026. Esta prueba nace de rastrear por qué la pantalla «Salud
Total» devolvía «Not Found», y de descubrir que no era un caso aislado.

**Lo que pasó, con fechas del repositorio:**

  · **09-05-2026**, commit `8f91087` y siguientes: se borran ocho routers que
    el portal usaba, y `3ccefd9` los reemplaza por cáscaras con prefijo
    `/_removed/` «para no romper los imports». Desde ese día, ocho pantallas
    del portal responden 404 — pero el código se ve ordenado.
  · **07-07-2026**, commit `0c15a71`: se borran las cáscaras. El mensaje dice
    «verificado cero callers, eliminación por AST». La verificación por AST
    solo miró el código **Python**. El que llamaba era el **JavaScript**.
  · **13-08-2026**: Yesid abre «Salud Total» y le sale «Not Found». Tres
    meses después.

Las ocho eran: salud_total, comentarios_thread, notas_privadas,
preset_filtros, push, auditor_forense y autopilot.

(«noticias» salió de esta lista el 19-08-2026: el ticker se quitó entero
porque su motor ya se había removido en mayo y solo quedaba la carcasa.)

**Lo que esta prueba hace:** lee las llamadas del JavaScript y comprueba que
cada una tenga su ruta montada. Es la verificación que faltó — la que mira el
frontend, no solo el backend.

`FALTANTES_CONOCIDAS` es una lista que **solo puede achicarse**. Si alguien
agrega una llamada a una ruta que no existe, la prueba falla; si repone una
de las que faltan, la prueba obliga a sacarla de la lista.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"

# Vacía: las nueve se repusieron el 13-08-2026. NUNCA agregar entradas acá
# para «pasar» la prueba — si una llamada falla, es porque falta la ruta y hay
# una pantalla del portal que no funciona.
FALTANTES_CONOCIDAS: set[str] = set()


def _rutas_montadas() -> set[str]:
    from app.main import app

    return {getattr(r, "path", "") for r in app.routes if getattr(r, "path", "")}


def _existe_exacta(url: str, montadas: set[str]) -> bool:
    if url in montadas:
        return True
    partes = url.strip("/").split("/")
    for m in montadas:
        mp = m.strip("/").split("/")
        if len(mp) != len(partes):
            continue
        if all(b.startswith("{") or a == b for a, b in zip(partes, mp)):
            return True
    return False


def _existe_prefijo(url: str, montadas: set[str]) -> bool:
    """El JavaScript concatena el identificador: `'/glosas/' + id`."""
    u = url.rstrip("/")
    return any(m.rstrip("/") == u or m.startswith(u + "/") for m in montadas)


def _llamadas_del_frontend() -> list[tuple[str, int, bool]]:
    """(url, línea, si concatena algo después)."""
    if not INDEX.exists():  # pragma: no cover
        pytest.skip("static/index.html no está en este entorno")
    texto = INDEX.read_text(encoding="utf-8", errors="ignore")
    salida = []
    for m in re.finditer(r"fetch\(\s*'(/[^'?]*)'(\s*[+,)])", texto):
        url = re.sub(r"/+$", "", m.group(1)) or "/"
        salida.append((url, texto[: m.start()].count("\n") + 1, m.group(2).strip().startswith("+")))
    return salida


def _faltantes() -> dict[str, int]:
    montadas = _rutas_montadas()
    falta: dict[str, int] = {}
    for url, linea, concatena in _llamadas_del_frontend():
        ok = _existe_prefijo(url, montadas) if concatena else _existe_exacta(url, montadas)
        if not ok:
            falta.setdefault(url, linea)
    return falta


class TestLaPantallaNoLlamaAlVacio:
    def test_la_prueba_encuentra_llamadas(self):
        """Guardia de la guardia: si el lector deja de encontrar llamadas, la
        prueba pasaría siempre sin revisar nada."""
        llamadas = _llamadas_del_frontend()
        assert len(llamadas) > 100, f"solo se leyeron {len(llamadas)} llamadas"

    def test_ninguna_llamada_nueva_apunta_a_una_ruta_inexistente(self):
        nuevas = {u: ln for u, ln in _faltantes().items() if u not in FALTANTES_CONOCIDAS}
        assert not nuevas, "la pantalla llama a rutas que no existen:\n" + "\n".join(
            f"  index.html:{ln} → {u}" for u, ln in sorted(nuevas.items())
        )

    def test_la_lista_de_pendientes_solo_puede_achicarse(self):
        """Si se repuso una ruta, hay que sacarla de FALTANTES_CONOCIDAS: si
        se queda, nadie se entera de que ya está resuelta."""
        faltan = set(_faltantes())
        resueltas = FALTANTES_CONOCIDAS - faltan
        assert not resueltas, (
            "estas rutas ya existen, sáquelas de FALTANTES_CONOCIDAS: "
            + ", ".join(sorted(resueltas))
        )


class TestLoQueSeRepuso:
    """Las nueve pantallas que volvieron. Los datos del auditor nunca se
    borraron: siguen sus tablas en la base, solo se había ido la puerta."""

    @pytest.mark.parametrize(
        "ruta",
        [
            "/comentarios-thread/glosa/{glosa_id}",
            "/notas-privadas/{glosa_id}",
            "/presets-filtros",
            "/api/salud-total/preview",
            "/push/public-key",
            "/chat-history/conversaciones",
            "/autopilot/preparar-dia",
            "/auditor-forense/upload",
            "/eventos/heartbeat",
            "/eventos/recientes",
        ],
    )
    def test_la_ruta_esta_montada(self, ruta):
        assert ruta in _rutas_montadas(), ruta

    @pytest.mark.parametrize(
        "modelo",
        [
            "ComentarioThreadRecord",
            "NotaPrivadaRecord",
            "PresetFiltroRecord",
            "PushSubscriptionRecord",
            "ChatConversacionRecord",
        ],
    )
    def test_la_tabla_del_auditor_sigue_existiendo(self, modelo):
        """Si el modelo no estuviera, reponer el router sería inventar una
        funcionalidad nueva en vez de devolver la que había."""
        import app.models.db as db

        assert hasattr(db, modelo), modelo

    def test_piden_sesion(self):
        """Son notas, comentarios y filtros del auditor sobre glosas
        concretas: por ahí no puede entrar cualquiera con la URL."""
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            for u in (
                "/comentarios-thread/glosa/1",
                "/notas-privadas/1",
                "/presets-filtros",
                "/chat-history/conversaciones",
                "/eventos/heartbeat",
                "/eventos/recientes",
            ):
                assert c.get(u).status_code in (401, 403), u

    def test_los_dos_forense_son_cosas_distintas(self):
        """`auditoria_forense` busca por IP y `auditor_forense` analiza los
        soportes de una factura. La limpieza de mayo los dio por el mismo y
        dejó la pantalla del Auditor Forense llamando al vacío."""
        rutas = _rutas_montadas()
        assert "/auditoria-forense/buscar-por-ip" in rutas
        assert "/auditor-forense/upload" in rutas

    def test_el_polling_y_el_sse_de_eventos_conviven(self):
        """Son mecanismos distintos con el mismo prefijo: el polling refresca
        los paneles cada pocos segundos, el SSE sigue una importación."""
        rutas = _rutas_montadas()
        assert {"/eventos/heartbeat", "/eventos/recientes"} <= rutas  # polling
        assert "/eventos/importar/{rec_id}" in rutas  # SSE
