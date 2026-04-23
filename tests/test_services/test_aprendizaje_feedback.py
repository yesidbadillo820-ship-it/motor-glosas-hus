"""Tests del aprendizaje por retroalimentación (Ronda 3)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.aprendizaje_feedback import (
    _extraer_argumento_del_dictamen,
    aprender_de_decision_eps,
)


def test_extraer_argumento_del_dictamen_con_marker():
    html = (
        "<div><table>...</table><h4>ARGUMENTACIÓN JURÍDICA</h4>"
        "<p>ESE HUS NO ACEPTA LA GLOSA TA0201 por lo siguiente: "
        "el valor facturado coincide con el contrato S-13-1-03-1-04958.</p>"
        "<div>Nota: Generado con asistencia de IA</div></div>"
    )
    arg = _extraer_argumento_del_dictamen(html)
    assert "ESE HUS NO ACEPTA" in arg
    assert "Nota:" not in arg


def test_extraer_argumento_sin_html_devuelve_vacio():
    assert _extraer_argumento_del_dictamen("") == ""
    assert _extraer_argumento_del_dictamen(None) == ""


def test_extraer_argumento_corta_en_soportes():
    html = (
        "<div>ARGUMENTACIÓN JURÍDICA ESE HUS NO ACEPTA LA GLOSA. "
        "📎 RELACIÓN DE SOPORTES APORTADOS table tbody</div>"
    )
    arg = _extraer_argumento_del_dictamen(html)
    assert "ESE HUS NO ACEPTA" in arg
    assert "SOPORTES" not in arg


def _fake_glosa(**kwargs):
    """Factory para GlosaRecord mock."""
    defaults = dict(
        id=1, eps="FAMISANAR EPS", codigo_glosa="TA0201",
        dictamen="<h4>ARGUMENTACIÓN JURÍDICA</h4> ESE HUS NO ACEPTA LA GLOSA "
                 "TA0201 porque el valor facturado coincide con el contrato "
                 "vigente. Se solicita levantamiento. " * 2,
        valor_recuperado=100000.0, modelo_ia="groq/llama-3.3",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_decision_aceptada_no_aprende():
    """Si HUS aceptó la glosa, no hay nada que promover."""
    db = MagicMock()
    g = _fake_glosa()
    r = aprender_de_decision_eps(db, g, "ACEPTADA", "test@hus.gov.co")
    assert r["accion"] == "skip"


def test_decision_levantada_con_modelo_fijo_skip():
    """Si el dictamen fue plantilla fija, no la duplicamos en Gold."""
    db = MagicMock()
    g = _fake_glosa(modelo_ia="texto_fijo")
    r = aprender_de_decision_eps(db, g, "LEVANTADA", "test@hus.gov.co")
    assert r["accion"] == "skip"


def test_decision_levantada_sin_recuperado_skip():
    db = MagicMock()
    g = _fake_glosa(valor_recuperado=0)
    r = aprender_de_decision_eps(db, g, "LEVANTADA", "test@hus.gov.co")
    assert r["accion"] == "skip"


def test_decision_levantada_promueve_a_gold():
    """Caso feliz: glosa levantada con valor recuperado → crea Gold."""
    db = MagicMock()
    # query chain devuelve vacío (no hay duplicado)
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = []
    q.first.return_value = None
    db.query.return_value = q

    g = _fake_glosa(id=42, valor_recuperado=100_000)
    r = aprender_de_decision_eps(db, g, "LEVANTADA", "test@hus.gov.co")
    assert r["accion"] == "promovida"
    # Se debe haber llamado db.add() con la Plantilla Gold
    assert db.add.called
    assert db.commit.called


def test_decision_sin_eps_skip():
    db = MagicMock()
    g = _fake_glosa(eps=None)
    r = aprender_de_decision_eps(db, g, "LEVANTADA", "test@hus.gov.co")
    assert r["accion"] == "skip"
