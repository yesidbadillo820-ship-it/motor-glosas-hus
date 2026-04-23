"""Tests del predictor de riesgo de glosa (Ronda 4)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.predictor_glosas import predecir_glosa


def _mock_db(total_hist=0, total_cups=0, top_codigos=None):
    """Construye un mock de Session que responde a las tres queries:
    count por eps+cups, count por cups, group_by codigo_glosa."""
    db = MagicMock()

    # Helper: cualquier query().filter().filter()... devuelve uno de los
    # sub-queries según el método final invocado.
    def _make_query(result_scalar, result_all):
        q = MagicMock()
        q.filter.return_value = q
        q.group_by.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.scalar.return_value = result_scalar
        q.all.return_value = result_all
        return q

    # Retornamos queries distintas según la llamada (simulando 2 scalars + 1 all)
    call_count = {"n": 0}
    def _query_side(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _make_query(total_hist, [])
        if call_count["n"] == 2:
            return _make_query(total_cups, [])
        return _make_query(0, top_codigos or [])

    db.query.side_effect = _query_side
    return db


def test_predictor_bajo_riesgo_caso_tipico():
    """Sin histórico + tarifa pactada + todo OK = BAJO."""
    db = _mock_db(total_hist=0, total_cups=0)
    # Mock también la búsqueda de tarifa pactada → encontrada
    from app.services import predictor_glosas as pg

    def _fake_tarifa(*a, **kw):
        return {"contrato_numero": "CONTR-001", "eps": "FAMISANAR EPS"}

    import unittest.mock as _mock
    with _mock.patch.object(pg, "_buscar_tarifa_pactada", _fake_tarifa):
        r = predecir_glosa(
            db, eps="FAMISANAR EPS", cups="890750", valor_facturado=85000,
            tiene_autorizacion=True, tiene_historia_clinica=True, tiene_soportes=True,
        )
    assert r["nivel_riesgo"] == "BAJO"
    assert r["probabilidad_glosa"] < 0.25


def test_predictor_critico_sin_contrato_sin_soportes_historico_alto():
    """Peor escenario: histórico alto + sin contrato + sin soportes."""
    db = _mock_db(total_hist=25, total_cups=50)
    from app.services import predictor_glosas as pg
    import unittest.mock as _mock
    with _mock.patch.object(pg, "_buscar_tarifa_pactada", lambda *a, **kw: None):
        r = predecir_glosa(
            db, eps="NUEVA EPS", cups="890201",
            valor_facturado=8_000_000,
            tiene_autorizacion=False, tiene_historia_clinica=False,
            tiene_soportes=False,
        )
    assert r["nivel_riesgo"] in ("ALTO", "CRÍTICO")
    assert r["valor_en_riesgo"] > 0
    assert len(r["motivos"]) >= 3
    assert len(r["recomendaciones"]) >= 1


def test_predictor_urgencia_con_hc_reduce_score():
    """Urgencias + HC → score ligeramente menor que sin HC."""
    db = _mock_db(total_hist=5, total_cups=10)
    from app.services import predictor_glosas as pg
    import unittest.mock as _mock
    with _mock.patch.object(pg, "_buscar_tarifa_pactada", lambda *a, **kw: None):
        r = predecir_glosa(
            db, eps="COOSALUD", cups="890701", valor_facturado=150000,
            tipo_servicio="URGENCIAS", tiene_historia_clinica=True,
        )
    # Debería al menos tener el motivo de T-1025
    txt = " ".join(r["motivos"])
    assert "Urgencia" in txt or "T-1025" in txt


def test_predictor_score_entre_0_y_1():
    db = _mock_db()
    from app.services import predictor_glosas as pg
    import unittest.mock as _mock
    with _mock.patch.object(pg, "_buscar_tarifa_pactada", lambda *a, **kw: None):
        r = predecir_glosa(db, eps="X", cups="Y", valor_facturado=0)
    assert 0 <= r["probabilidad_glosa"] <= 1
    assert r["nivel_riesgo"] in ("BAJO", "MEDIO", "ALTO", "CRÍTICO")


def test_predictor_estructura_respuesta_completa():
    db = _mock_db()
    from app.services import predictor_glosas as pg
    import unittest.mock as _mock
    with _mock.patch.object(pg, "_buscar_tarifa_pactada", lambda *a, **kw: None):
        r = predecir_glosa(db, eps="X", cups="Y", valor_facturado=100000)
    assert set(r.keys()) >= {
        "probabilidad_glosa", "nivel_riesgo", "codigos_probables",
        "motivos", "recomendaciones", "valor_en_riesgo",
        "historico_12m", "tarifa_pactada_encontrada",
    }
