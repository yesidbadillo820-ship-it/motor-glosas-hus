"""Tests del digest ejecutivo (Ronda 19)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.services.digest_ejecutivo import (
    _ventana,
    _top_eps,
    generar_digest,
    formatear_digest_texto,
    formatear_digest_html,
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


def _g(db, **kw):
    defaults = dict(
        eps="FAMISANAR EPS",
        paciente="X",
        factura="F",
        codigo_glosa="TA0201",
        valor_objetado=100_000.0,
        valor_recuperado=0.0,
        estado="PENDIENTE",
        dias_restantes=10,
        creado_en=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    g = GlosaRecord(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ─── _ventana ──────────────────────────────────────────────────────────────

class TestVentana:
    def test_dia(self):
        desde, hasta = _ventana("dia")
        assert hasta > desde
        assert (hasta - desde) <= timedelta(days=1)

    def test_semana(self):
        desde, hasta = _ventana("semana")
        assert (hasta - desde) <= timedelta(days=7, hours=1)

    def test_mes(self):
        desde, hasta = _ventana("mes")
        assert (hasta - desde) >= timedelta(days=29)


# ─── _top_eps ──────────────────────────────────────────────────────────────

class TestTopEps:
    def test_sin_glosas(self, db_session):
        desde, hasta = _ventana("dia")
        assert _top_eps(db_session, desde, hasta) == []

    def test_ordena_por_cantidad(self, db_session):
        for _ in range(3):
            _g(db_session, eps="EPS-A", factura="FA")
        for _ in range(5):
            _g(db_session, eps="EPS-B", factura="FB")
        desde, hasta = _ventana("dia")
        top = _top_eps(db_session, desde, hasta)
        assert len(top) == 2
        assert top[0]["eps"] == "EPS-B"
        assert top[0]["cantidad"] == 5
        assert top[1]["eps"] == "EPS-A"


# ─── generar_digest ────────────────────────────────────────────────────────

class TestGenerarDigest:
    def test_estructura_basica(self, db_session):
        d = generar_digest(db_session, periodo="dia")
        assert d["periodo"] == "dia"
        assert "indicadores" in d
        assert "operativo" in d
        assert "autopilot" in d
        assert "top_eps" in d
        assert "alertas" in d
        assert "estado_general" in d

    def test_indicadores_sin_data(self, db_session):
        d = generar_digest(db_session, periodo="dia")
        assert d["indicadores"]["radicadas"] == 0
        assert d["indicadores"]["valor_objetado"] == 0.0
        assert d["indicadores"]["tasa_recuperacion"] == 0.0

    def test_indicadores_con_radicadas(self, db_session):
        _g(db_session, valor_objetado=500_000)
        _g(db_session, valor_objetado=300_000, factura="F2")
        d = generar_digest(db_session, periodo="dia")
        assert d["indicadores"]["radicadas"] == 2
        assert d["indicadores"]["valor_objetado"] == 800_000.0

    def test_tasa_recuperacion_calculada(self, db_session):
        ahora = datetime.now(timezone.utc)
        _g(
            db_session,
            valor_objetado=1_000_000,
            valor_recuperado=400_000,
            fecha_decision_eps=ahora,
        )
        d = generar_digest(db_session, periodo="dia")
        assert d["indicadores"]["tasa_recuperacion"] == 0.4

    def test_conteo_autopilot_suma(self, db_session):
        _g(db_session, factura="F-A", dictamen="<p>Ley 1438.</p>" * 30)
        _g(db_session, factura="F-B", dictamen="")
        d = generar_digest(db_session, periodo="dia")
        total = sum(d["autopilot"].values())
        assert total == 2


# ─── Formatters ────────────────────────────────────────────────────────────

class TestFormatters:
    def test_texto_contiene_secciones(self, db_session):
        _g(db_session, valor_objetado=500_000)
        d = generar_digest(db_session, periodo="dia")
        t = formatear_digest_texto(d)
        assert "RESUMEN" in t
        assert "Autopilot" in t
        assert "Radicadas" in t

    def test_texto_con_top_eps(self, db_session):
        _g(db_session, eps="FAMISANAR")
        d = generar_digest(db_session, periodo="dia")
        t = formatear_digest_texto(d)
        assert "Top EPS" in t

    def test_html_es_string_con_etiquetas(self, db_session):
        _g(db_session)
        d = generar_digest(db_session, periodo="dia")
        h = formatear_digest_html(d)
        assert "<h2>" in h
        assert "<ul>" in h
        assert "Autopilot" in h
