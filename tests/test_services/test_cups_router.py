"""Tests del router /cups (Ronda 50 Paso 4)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import TarifaContratadaRecord


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    # Seed datos típicos
    s.add(TarifaContratadaRecord(
        eps="DISPENSARIO MEDICO DMBUG", codigo_cups="890348",
        codigo_ips="39147B-18",
        descripcion="CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA",
        valor_pactado=231556, modalidad="TARIFA PROPIA",
        contrato_numero="440-DIGSA/DMBUG-2025", activa=1,
        creado_en=datetime.now(timezone.utc),
    ))
    s.add(TarifaContratadaRecord(
        eps="FAMISANAR EPS", codigo_cups="890750",
        descripcion="CONSULTA DE URGENCIAS, POR ESPECIALISTA EN GINECOLOGIA Y OBSTETRICIA",
        valor_pactado=114900, modalidad="SOAT UVB VIGENTE", activa=1,
        creado_en=datetime.now(timezone.utc),
    ))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def test_import_cups_router_ok():
    """El router existe y es importable."""
    from app.api.routers.cups import router, buscar_cups, detalle_cups
    assert router is not None
    assert buscar_cups is not None
    assert detalle_cups is not None


def test_buscar_por_codigo_cups_exacto(db):
    from app.api.routers.cups import buscar_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    r = buscar_cups(q="890348", limite=10, eps=None, db=db, current_user=user)
    assert r["total"] >= 1
    assert r["resultados"][0]["codigo_cups"] == "890348"
    assert r["resultados"][0]["tipo_match"] == "codigo_cups_exacto"


def test_buscar_por_codigo_ips_devuelve_tarifa(db):
    from app.api.routers.cups import buscar_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    r = buscar_cups(q="39147B-18", limite=10, eps=None, db=db, current_user=user)
    assert r["total"] >= 1
    # Puede venir como codigo_ips_exacto o homologacion_2641
    assert any(f["codigo_cups"] == "890348" for f in r["resultados"])


def test_buscar_por_descripcion(db):
    from app.api.routers.cups import buscar_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    # Usamos "CONSULTA" que está literal (sin tildes) en ambas descripciones
    r = buscar_cups(q="CONSULTA", limite=10, eps=None, db=db, current_user=user)
    assert r["total"] >= 1
    assert any("CONSULTA" in (f["descripcion"] or "").upper() for f in r["resultados"])


def test_filtro_por_eps(db):
    from app.api.routers.cups import buscar_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    r = buscar_cups(q="CONSULTA", limite=10, eps="FAMISANAR", db=db, current_user=user)
    # Solo debe devolver Famisanar
    for fila in r["resultados"]:
        assert "FAMISANAR" in (fila["eps"] or "").upper() or fila["eps"] == "—"


def test_detalle_cups_con_contratos(db):
    from app.api.routers.cups import detalle_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    r = detalle_cups("890348", db=db, current_user=user)
    assert r["total_contratos"] == 1
    assert r["contratos_que_lo_incluyen"][0]["eps"] == "DISPENSARIO MEDICO DMBUG"
    assert r["contratos_que_lo_incluyen"][0]["valor_pactado"] == 231556


def test_detalle_cups_inexistente(db):
    from app.api.routers.cups import detalle_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    r = detalle_cups("999999", db=db, current_user=user)
    assert r["total_contratos"] == 0


# ─── Ronda 51 Paso 2: búsqueda insensible a tildes ──────────────────────

def test_buscar_sin_tildes_encuentra_con_tilde(db):
    """'GENETICA' debe encontrar 'GENÉTICA' aun cuando BD tiene tildes."""
    from app.api.routers.cups import buscar_cups
    from unittest.mock import MagicMock
    user = MagicMock(email="test@hus.com")
    r = buscar_cups(q="GENETICA", limite=10, eps=None, db=db, current_user=user)
    assert r["total"] >= 1
    # Debe encontrar 'CONSULTA DE CONTROL O DE SEGUIMIENTO POR ESPECIALISTA EN GENÉTICA MÉDICA'
    assert any("GEN" in _sin_tildes(f["descripcion"] or "") for f in r["resultados"])


def test_normalizacion_quita_tildes():
    from app.api.routers.cups import _sin_tildes
    assert _sin_tildes("GENÉTICA") == "GENETICA"
    assert _sin_tildes("MÉDICO") == "MEDICO"
    assert _sin_tildes("ñandú") == "NANDU"
    assert _sin_tildes("") == ""
    assert _sin_tildes(None) == ""

from app.api.routers.cups import _sin_tildes  # para el primer test
