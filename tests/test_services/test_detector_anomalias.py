"""Tests del detector de anomalías (Ronda 16)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.services.detector_anomalias import (
    detectar_duplicados,
    detectar_patron_sospechoso_eps,
    detectar_valor_anomalo,
    resumen_anomalias,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


def _crear_glosa(db, **kwargs):
    defaults = dict(
        eps="FAMISANAR EPS",
        paciente="X",
        factura="FAC-001",
        codigo_glosa="TA0201",
        valor_objetado=100_000.0,
        estado="PENDIENTE",
        dias_restantes=10,
        creado_en=datetime.now(timezone.utc),
        cups_servicio="890701",
    )
    defaults.update(kwargs)
    g = GlosaRecord(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ─── Duplicados ────────────────────────────────────────────────────────────

class TestDuplicados:
    def test_sin_duplicados_retorna_vacio(self, db_session):
        _crear_glosa(db_session, factura="F-1", cups_servicio="890701")
        _crear_glosa(db_session, factura="F-2", cups_servicio="890701")
        assert detectar_duplicados(db_session) == []

    def test_detecta_factura_cups_repetida(self, db_session):
        _crear_glosa(db_session, factura="F-10", cups_servicio="890701")
        _crear_glosa(db_session, factura="F-10", cups_servicio="890701")
        res = detectar_duplicados(db_session)
        assert len(res) == 1
        assert res[0].tipo == "duplicado"
        assert res[0].entidad["factura"] == "F-10"
        assert res[0].entidad["n"] == 2
        assert res[0].severidad == "MEDIA"

    def test_triplicado_es_alta(self, db_session):
        for _ in range(3):
            _crear_glosa(db_session, factura="F-20", cups_servicio="890701")
        res = detectar_duplicados(db_session)
        assert len(res) == 1
        assert res[0].severidad == "ALTA"
        assert res[0].entidad["n"] == 3

    def test_ignora_factura_na(self, db_session):
        _crear_glosa(db_session, factura="N/A", cups_servicio="890701")
        _crear_glosa(db_session, factura="N/A", cups_servicio="890701")
        assert detectar_duplicados(db_session) == []

    def test_eps_distinta_no_es_duplicado(self, db_session):
        _crear_glosa(db_session, factura="F-30", eps="SANITAS", cups_servicio="890701")
        _crear_glosa(db_session, factura="F-30", eps="SURA", cups_servicio="890701")
        assert detectar_duplicados(db_session) == []


# ─── Patrón sospechoso EPS ─────────────────────────────────────────────────

class TestPatronEps:
    def test_eps_sin_data_previa_no_marca(self, db_session):
        # Solo 2 glosas en periodo reciente, nada antes
        for _ in range(2):
            _crear_glosa(db_session, eps="NUEVA")
        assert detectar_patron_sospechoso_eps(db_session) == []

    def test_salto_volumen_grande_marca_alta(self, db_session):
        ahora = datetime.now(timezone.utc)
        # Periodo previo (45d atrás): 6 glosas
        for i in range(6):
            _crear_glosa(
                db_session,
                eps="EPS_X",
                factura=f"FP-{i}",
                creado_en=ahora - timedelta(days=45),
            )
        # Periodo reciente (5d atrás): 12 glosas → +100 %
        for i in range(12):
            _crear_glosa(
                db_session,
                eps="EPS_X",
                factura=f"FR-{i}",
                creado_en=ahora - timedelta(days=5),
            )
        res = detectar_patron_sospechoso_eps(db_session, ventana_dias=30)
        assert len(res) == 1
        assert res[0].severidad == "ALTA"
        assert res[0].entidad["eps"] == "EPS_X"
        assert res[0].entidad["salto_volumen"] > 0.6


# ─── Valor anómalo ─────────────────────────────────────────────────────────

class TestValorAnomalo:
    def test_sin_cups_retorna_none(self, db_session):
        g = _crear_glosa(db_session, cups_servicio=None, valor_objetado=100_000)
        assert detectar_valor_anomalo(db_session, g) is None

    def test_muestra_pequena_retorna_none(self, db_session):
        g = _crear_glosa(db_session, cups_servicio="999999", valor_objetado=100_000)
        assert detectar_valor_anomalo(db_session, g) is None

    def test_valor_extremo_detectado(self, db_session):
        # 15 glosas del mismo CUPS en ~100k
        for i in range(15):
            _crear_glosa(
                db_session,
                cups_servicio="890701",
                valor_objetado=100_000.0 + i * 1000,
                factura=f"F-{i}",
            )
        # Una glosa con valor monstruosamente alto
        g = _crear_glosa(
            db_session,
            cups_servicio="890701",
            valor_objetado=10_000_000.0,
            factura="F-BIG",
        )
        res = detectar_valor_anomalo(db_session, g)
        assert res is not None
        assert res.tipo == "valor_anomalo"
        assert res.severidad == "ALTA"
        assert res.entidad["z_score"] > 3


# ─── Resumen dashboard ─────────────────────────────────────────────────────

def test_resumen_anomalias_estructura(db_session):
    _crear_glosa(db_session, factura="F-DUP", cups_servicio="890701")
    _crear_glosa(db_session, factura="F-DUP", cups_servicio="890701")
    r = resumen_anomalias(db_session, ventana_dias=30)
    assert "totales" in r
    assert r["totales"]["duplicados"] == 1
    assert "generado_en" in r
    assert "duplicados" in r
    assert isinstance(r["duplicados"], list)
