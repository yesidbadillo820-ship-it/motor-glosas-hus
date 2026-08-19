"""El panel de progreso no se cierra con el dictamen a medias — 19-08-2026.

Mientras el motor analiza una glosa, abajo a la derecha sale un panel negro
que va contando qué está haciendo. Ese panel se cerraba solo a los 3 minutos.

Alcanzaba de sobra cuando el análisis no leía el expediente. Pero desde que el
Auditor Forense corre dentro de «Analizar glosa», la lectura de los soportes se
toma 1-2 minutos ANTES de que empiece a redactarse el dictamen. Con 3 minutos
el panel desaparecía con el trabajo a medias y parecía que se había caído — y
un auditor que cree que se cayó, recarga y pierde lo que llevaba.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


def _html() -> str:
    if not INDEX.exists():  # pragma: no cover
        pytest.skip("static/index.html no está en este entorno")
    return INDEX.read_text(encoding="utf-8", errors="ignore")


def test_el_panel_aguanta_mas_que_la_lectura_del_expediente():
    m = re.search(r"setTimeout\(cerrar,\s*(\d+)\)", _html())
    assert m, "no se encontró el cierre automático del panel de progreso"
    ms = int(m.group(1))
    # 2 min de forense + el dictamen, con margen.
    assert ms >= 300_000, f"el panel se cierra a los {ms / 1000:.0f}s, antes de terminar"


def test_la_pantalla_avisa_que_esta_leyendo_los_soportes():
    """Sin este aviso, 1-2 minutos de silencio se leen como «se colgó»."""
    texto = _html()
    assert "auditor_forense_inicio: function" in texto
    assert "1-2 min" in texto, "no se le dice al auditor cuánto va a esperar"


def test_el_motor_manda_ese_aviso_antes_de_ponerse_a_leer():
    fuente = (RAIZ / "app" / "api" / "routers" / "analizar.py").read_text(encoding="utf-8")
    assert '"auditor_forense_inicio"' in fuente
    assert fuente.index('"auditor_forense_inicio"') < fuente.index(
        "_ev = await evidencia_para_dictamen("
    )


def test_el_aviso_no_se_pierde_por_el_camino():
    """`publicar()` no puede tener una lista blanca que lo bote."""
    servicio = (RAIZ / "app" / "services" / "progreso_analisis.py").read_text(encoding="utf-8")
    for palabra in ("ETAPAS_PERMITIDAS", "whitelist", "ETAPAS_VALIDAS"):
        assert palabra not in servicio, f"«{palabra}» filtraría el aviso nuevo"
