"""Tests del servicio de batch aprobación autopilot (Ronda 34).

Prueba la lógica interna — el router en sí se prueba con el TestClient
en test_api. Acá validamos que evaluar_glosa_autopilot + actualización
de estado sea coherente.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord, PlantillaGoldRecord
from app.services.autopilot_service import evaluar_glosa_autopilot


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try: yield s
    finally: s.close()


def test_texto_fijo_ratificada_es_lista_enviar(db):
    """Una glosa con texto_fijo RATIFICADA siempre debe clasificarse LISTA_ENVIAR."""
    g = GlosaRecord(
        eps="FAMISANAR", paciente="X", factura="F", codigo_glosa="TA0201",
        valor_objetado=100_000, estado="RATIFICADA",
        dictamen="<p>RATIFICADA — texto canónico</p>",
        modelo_ia="pre-analisis/texto_fijo/RATIFICADA",
        creado_en=datetime.now(timezone.utc),
    )
    db.add(g); db.commit(); db.refresh(g)
    res = evaluar_glosa_autopilot(db, g)
    assert res.estado == "LISTA_ENVIAR"
    assert res.confianza >= 0.90


def test_dictamen_vacio_es_intervenir(db):
    g = GlosaRecord(
        eps="FAMISANAR", paciente="X", factura="F", codigo_glosa="TA0201",
        valor_objetado=100_000, estado="PENDIENTE",
        dictamen="", creado_en=datetime.now(timezone.utc),
    )
    db.add(g); db.commit(); db.refresh(g)
    res = evaluar_glosa_autopilot(db, g)
    assert res.estado == "INTERVENIR"


def test_autopilot_devuelve_detalle_para_batch(db):
    """El dict resultado debe traer estado + confianza (campos que usa batch-aprobar)."""
    g = GlosaRecord(
        eps="FAMISANAR", paciente="X", factura="F", codigo_glosa="TA0201",
        valor_objetado=100_000, estado="RATIFICADA",
        dictamen="<p>OK</p>", modelo_ia="pre-analisis/texto_fijo/RATIFICADA",
        creado_en=datetime.now(timezone.utc),
    )
    db.add(g); db.commit(); db.refresh(g)
    res = evaluar_glosa_autopilot(db, g)
    assert hasattr(res, "estado")
    assert hasattr(res, "confianza")
    assert isinstance(res.confianza, (int, float))
