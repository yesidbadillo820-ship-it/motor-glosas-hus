"""Ronda 23 (jul-2026) — el motor deja de decir "SIN CONTRATO PACTADO"
cuando SÍ hay contrato/cláusulas cargadas en la BD.

Causa raíz (investigación 1-jul): get_contrato solo leía el catálogo
estático CONTRATOS_HUS (~15 EPS). Una EPS con contrato cargado en la BD
pero fuera del catálogo caía al fallback "SIN CONTRATO PACTADO",
negando un contrato real. La presencia de cláusulas PRUEBA que hay
contrato.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database
from app.database import Base
from app.models.db import ClausulaContrato, ContratoRecord


@pytest.fixture
def db_en_memoria(monkeypatch):
    """SessionLocal apuntando a un SQLite en memoria, para probar la
    lectura de contratos desde la BD sin tocar la BD real."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", Session)
    return Session


def test_eps_con_numero_de_contrato_en_bd_no_dice_sin_contrato(db_en_memoria):
    s = db_en_memoria()
    s.add(
        ContratoRecord(
            eps="PRUEBA EPS BD",
            detalles="x",
            numero_contrato="CTR-2024-PRUEBA-HUS",
        )
    )
    s.commit()
    s.close()

    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("PRUEBA EPS BD")
    assert ficha["numero"] == "CTR-2024-PRUEBA-HUS"
    assert "SIN CONTRATO" not in ficha["numero"].upper()


def test_eps_con_clausulas_pero_sin_numero_usa_referencia_neutra(db_en_memoria):
    """Hay cláusulas (⇒ existe contrato) pero sin número cargado → referencia
    neutra, JAMÁS 'SIN CONTRATO PACTADO'."""
    s = db_en_memoria()
    s.add(ContratoRecord(eps="PRUEBA EPS BD", detalles="x"))  # sin numero_contrato
    s.add(
        ClausulaContrato(
            eps="PRUEBA EPS BD",
            numero_clausula="9",
            tema="CO",
            titulo="Junta médica",
            texto_literal="La cláusula novena exige junta médica de especialistas.",
        )
    )
    s.commit()
    s.close()

    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("PRUEBA EPS BD")
    assert "SIN CONTRATO" not in ficha["numero"].upper()
    assert "vigente entre las partes" in ficha["numero"].lower()


def test_eps_sin_nada_en_bd_mantiene_sin_contrato(db_en_memoria):
    """Sin datos en BD ni catálogo → sigue diciendo SIN CONTRATO (no regresa)."""
    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("EPS INEXISTENTE ZZZ 999")
    assert ficha["numero"] == "SIN CONTRATO PACTADO"


def test_eps_generica_sigue_sin_contrato(db_en_memoria):
    """'OTRA / SIN DEFINIR' nunca inventa contrato."""
    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("OTRA / SIN DEFINIR")
    assert ficha["numero"] == "SIN CONTRATO PACTADO"


def test_clausulas_reales_se_inyectan_para_citar(db_en_memoria):
    """Sanity: si hay cláusula en BD, get_clausulas_para_glosa la devuelve
    para que la IA la cite textualmente."""
    s = db_en_memoria()
    s.add(
        ClausulaContrato(
            eps="PRUEBA EPS BD",
            numero_clausula="24",
            tema="TA",
            titulo="Tarifa pactada",
            texto_literal="El valor se liquidará a SOAT menos diez por ciento (10%).",
        )
    )
    s.commit()
    s.close()

    from app.services.glosa_ia_prompts import get_clausulas_para_glosa

    cls = get_clausulas_para_glosa("PRUEBA EPS BD", "TA0201")
    assert any("SOAT menos diez" in c["texto_literal"] for c in cls)


def test_eps_corta_empareja_con_razon_social_completa(db_en_memoria):
    """La glosa trae 'AURORA' pero la cláusula está bajo la razón social
    completa 'SEGUROS DE VIDA AURORA S.A.'. El match flexible debe hallarla
    (antes el == exacto la perdía y la IA no citaba nada)."""
    s = db_en_memoria()
    s.add(
        ClausulaContrato(
            eps="SEGUROS DE VIDA AURORA S.A.",
            numero_clausula="Primera, Parágrafo Cuarto",
            tema="TA",
            titulo="Tarifa pactada",
            texto_literal="Los servicios se facturarán a SOAT – 3% en SMLMV.",
        )
    )
    s.commit()
    s.close()

    from app.services.glosa_ia_prompts import get_clausulas_para_glosa

    cls = get_clausulas_para_glosa("AURORA", "TA0101")
    assert any("SOAT – 3%" in c["texto_literal"] for c in cls), (
        "El match flexible no encontró la cláusula bajo la razón social completa"
    )
