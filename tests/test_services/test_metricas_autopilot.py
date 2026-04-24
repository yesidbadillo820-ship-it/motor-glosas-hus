"""Tests de métricas de autopilot (Ronda 32)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.services.metricas_autopilot import metricas_autopilot


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try: yield s
    finally: s.close()


def _g(db, **kw):
    d = dict(
        eps="FAMISANAR", paciente="X", factura="F",
        codigo_glosa="TA0201", valor_objetado=100_000,
        estado="PENDIENTE", creado_en=datetime.now(timezone.utc),
    )
    d.update(kw)
    g = GlosaRecord(**d); db.add(g); db.commit(); db.refresh(g)
    return g


def test_sin_glosas(db):
    r = metricas_autopilot(db, periodo="hoy")
    assert r["cerradas_por_ia"]["total"] == 0
    assert r["ahorro"]["usd_estimados"] == 0


def test_cuenta_texto_fijo_ratificada(db):
    _g(db, modelo_ia="pre-analisis/texto_fijo/RATIFICADA", valor_objetado=500_000)
    r = metricas_autopilot(db, periodo="hoy")
    assert r["cerradas_por_ia"]["total"] == 1
    assert r["desglose"]["texto_fijo_ratificada"]["cantidad"] == 1
    assert r["desglose"]["texto_fijo_ratificada"]["valor"] == 500_000


def test_cuenta_texto_fijo_extemporanea(db):
    _g(db, modelo_ia="pre-analisis/texto_fijo/EXTEMPORANEA", valor_objetado=200_000)
    r = metricas_autopilot(db, periodo="hoy")
    assert r["desglose"]["texto_fijo_extemporanea"]["cantidad"] == 1


def test_cuenta_tarifa_match(db):
    _g(db, modelo_ia="pre-analisis/texto_fijo")
    r = metricas_autopilot(db, periodo="hoy")
    assert r["desglose"]["tarifa_match_perfecto"]["cantidad"] == 1


def test_suma_ahorro_estimado(db):
    for _ in range(5):
        _g(db, modelo_ia="pre-analisis/texto_fijo/RATIFICADA", factura="F"+str(_))
    r = metricas_autopilot(db, periodo="hoy")
    # 5 * 8000 tokens = 40k tokens, ~0.06 USD
    assert r["ahorro"]["tokens_estimados"] == 40_000
    assert r["ahorro"]["usd_estimados"] >= 0.05


def test_ignora_dictamenes_IA_normales(db):
    _g(db, modelo_ia="anthropic/claude-sonnet")
    r = metricas_autopilot(db, periodo="hoy")
    assert r["cerradas_por_ia"]["total"] == 0


def test_pct_sobre_creadas(db):
    _g(db, modelo_ia="pre-analisis/texto_fijo/RATIFICADA", factura="F1")
    _g(db, modelo_ia="anthropic/claude-sonnet", factura="F2")
    r = metricas_autopilot(db, periodo="hoy")
    # 1 de 2 = 50%
    assert r["cerradas_por_ia"]["pct_sobre_creadas"] == 0.5
