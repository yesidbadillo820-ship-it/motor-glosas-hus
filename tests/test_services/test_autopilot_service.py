"""Tests del autopilot de recomendación (Ronda 18)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord, PlantillaGoldRecord
from app.services.autopilot_service import (
    ESTADOS,
    _tiene_plantilla_gold,
    _calidad_dictamen,
    evaluar_glosa_autopilot,
    evaluar_bandeja,
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


def _glosa_base(db, **kw):
    defaults = dict(
        eps="FAMISANAR EPS",
        paciente="X",
        factura="F-1",
        codigo_glosa="TA0201",
        valor_objetado=100_000.0,
        estado="PENDIENTE",
        dias_restantes=10,
        creado_en=datetime.now(timezone.utc),
        dictamen="<p>Dictamen completo con Ley 1438/2011 Art. 57 y Resolución 2284/2023.</p>" * 20,
    )
    defaults.update(kw)
    g = GlosaRecord(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _crear_gold(db, eps, codigo):
    p = PlantillaGoldRecord(
        eps=eps, codigo_glosa=codigo, tipo="TA", titulo="Gold",
        argumento="Argumento que ganó antes.", activa=1,
    )
    db.add(p)
    db.commit()


# ─── Helpers ───────────────────────────────────────────────────────────────

class TestHelpers:
    def test_tiene_plantilla_gold_count(self, db_session):
        _crear_gold(db_session, "FAMISANAR EPS", "TA0201")
        _crear_gold(db_session, "FAMISANAR EPS", "TA0201")
        assert _tiene_plantilla_gold(db_session, "FAMISANAR", "TA0201") == 2

    def test_tiene_plantilla_gold_sin_match(self, db_session):
        assert _tiene_plantilla_gold(db_session, "SANITAS", "TA0201") == 0

    def test_tiene_plantilla_gold_vacio(self, db_session):
        assert _tiene_plantilla_gold(db_session, "", "") == 0

    def test_calidad_dictamen_vacio(self):
        r = _calidad_dictamen("")
        assert r["longitud"] == 0
        assert not r["tiene_contenido"]

    def test_calidad_dictamen_con_citas(self):
        html = "<p>Ley 1438. Resolución 2284. Artículo 57.</p>" * 30
        r = _calidad_dictamen(html)
        assert r["tiene_contenido"]
        assert r["citas"] >= 3


# ─── evaluar_glosa_autopilot ───────────────────────────────────────────────

class TestEvaluarGlosa:
    def test_detecta_gold_y_dictamen_en_razones(self, db_session):
        """Con Gold + dictamen rico, las razones a favor las reflejan."""
        _crear_gold(db_session, "FAMISANAR EPS", "TA0201")
        g = _glosa_base(
            db_session,
            eps="FAMISANAR EPS",
            codigo_glosa="TA0201",
            modelo_ia="anthropic/claude-sonnet",
        )
        res = evaluar_glosa_autopilot(db_session, g)
        assert res.estado in ESTADOS
        assert any("Gold" in r for r in res.razones_a_favor)
        assert any("Dictamen con" in r for r in res.razones_a_favor)

    def test_intervenir_dictamen_vacio(self, db_session):
        g = _glosa_base(db_session, dictamen="")
        res = evaluar_glosa_autopilot(db_session, g)
        assert res.estado == "INTERVENIR"
        assert any("vac" in r.lower() or "corto" in r.lower() for r in res.razones_en_contra)

    def test_sin_gold_sugiere_bajar_estado(self, db_session):
        g = _glosa_base(db_session, eps="EPS_NUEVA", codigo_glosa="TA0201")
        res = evaluar_glosa_autopilot(db_session, g)
        # Sin Gold ni histórico, debería estar en REVISAR/CASI_LISTA/INTERVENIR
        assert res.estado in ESTADOS
        assert any("Sin plantilla Gold" in r for r in res.razones_en_contra)

    def test_resultado_incluye_detalle_ml(self, db_session):
        g = _glosa_base(db_session)
        res = evaluar_glosa_autopilot(db_session, g)
        assert "prediccion_ml" in res.detalle
        assert "probabilidad_ratificacion" in res.detalle["prediccion_ml"]

    def test_confianza_en_rango(self, db_session):
        g = _glosa_base(db_session)
        res = evaluar_glosa_autopilot(db_session, g)
        assert 0.0 <= res.confianza <= 1.0


# ─── evaluar_bandeja ───────────────────────────────────────────────────────

class TestEvaluarBandeja:
    def test_bandeja_vacia(self, db_session):
        r = evaluar_bandeja(db_session, auditor_email="juan@hus.com")
        assert r["total_evaluadas"] == 0
        assert sum(r["conteo_por_estado"].values()) == 0

    def test_bandeja_filtra_por_auditor(self, db_session):
        _glosa_base(db_session, auditor_email="juan@hus.com")
        _glosa_base(db_session, auditor_email="ana@hus.com", factura="F-2")
        r = evaluar_bandeja(db_session, auditor_email="juan@hus.com")
        assert r["total_evaluadas"] == 1

    def test_bandeja_solo_pendientes(self, db_session):
        _glosa_base(db_session, estado="RESPONDIDA", factura="F-resp")
        _glosa_base(db_session, estado="PENDIENTE", factura="F-pend")
        r = evaluar_bandeja(db_session)
        assert r["total_evaluadas"] == 1

    def test_bandeja_conteo_suma_total(self, db_session):
        for i in range(4):
            _glosa_base(db_session, factura=f"F-{i}")
        r = evaluar_bandeja(db_session)
        assert sum(r["conteo_por_estado"].values()) == r["total_evaluadas"] == 4
        for estado in r["conteo_por_estado"]:
            assert estado in ESTADOS
