"""Tests del batch retro-aplicación de texto fijo (Ronda 22)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.services.texto_fijo_batch import retro_aplicar


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


def _crear(db, **kw):
    defaults = dict(
        eps="FAMISANAR", paciente="X", factura="F",
        codigo_glosa="TA0201", valor_objetado=100_000,
        estado="PENDIENTE", creado_en=datetime.now(timezone.utc),
    )
    defaults.update(kw)
    g = GlosaRecord(**defaults)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


class TestDryRun:
    def test_sin_candidatas(self, db_session):
        r = retro_aplicar(db_session, dry_run=True)
        assert r["dry_run"] is True
        assert r["total_analizadas"] == 0
        assert r["aplicarian_ratificada"] == 0

    def test_detecta_ratificada_en_dry_run(self, db_session):
        _crear(db_session, estado="RATIFICADA")
        r = retro_aplicar(db_session, dry_run=True)
        assert r["aplicarian_ratificada"] == 1
        # No debería haber mutado
        assert r["aplicadas"] == 0

    def test_detecta_extemporanea_en_dry_run(self, db_session):
        _crear(db_session, dias_radicacion_dgh=25)
        r = retro_aplicar(db_session, dry_run=True)
        assert r["aplicarian_extemporanea"] == 1

    def test_prioridad_ratificada_sobre_extemporanea(self, db_session):
        """Caso con ambas condiciones: cuenta como RATIFICADA, no EXTEMPORANEA."""
        _crear(db_session, estado="RATIFICADA", dias_radicacion_dgh=30)
        r = retro_aplicar(db_session, dry_run=True)
        assert r["aplicarian_ratificada"] == 1
        assert r["aplicarian_extemporanea"] == 0


class TestEjecucionReal:
    def test_aplica_ratificada_real(self, db_session):
        g = _crear(db_session, estado="RATIFICADA")
        r = retro_aplicar(db_session, dry_run=False)
        assert r["aplicadas"] == 1
        db_session.refresh(g)
        assert "RATIFICADA" in g.dictamen.upper()
        assert "texto_fijo" in (g.modelo_ia or "").lower()

    def test_segunda_corrida_es_idempotente(self, db_session):
        _crear(db_session, estado="RATIFICADA")
        r1 = retro_aplicar(db_session, dry_run=False)
        assert r1["aplicadas"] == 1
        r2 = retro_aplicar(db_session, dry_run=False)
        # Ya está aplicado → skip
        assert r2["aplicadas"] == 0
        assert r2["skip_por_idempotencia"] == 1

    def test_respeta_dictamen_IA_existente(self, db_session):
        _crear(
            db_session,
            estado="PENDIENTE",
            dias_radicacion_dgh=25,
            dictamen="<p>Dictamen IA existente largo</p>",
            modelo_ia="anthropic/claude-sonnet",
        )
        r = retro_aplicar(db_session, dry_run=False)
        # El detector lo identifica como extemporánea pero no lo aplica
        assert r["aplicarian_extemporanea"] == 1
        assert r["skip_por_idempotencia"] == 1
        assert r["aplicadas"] == 0

    def test_excluye_resueltas(self, db_session):
        _crear(db_session, estado="RESUELTA")
        _crear(db_session, estado="ARCHIVADA", factura="F2")
        r = retro_aplicar(db_session, dry_run=True)
        assert r["total_analizadas"] == 0

    def test_limite_aplicado(self, db_session):
        for i in range(10):
            _crear(db_session, estado="RATIFICADA", factura=f"F-{i}")
        r = retro_aplicar(db_session, dry_run=True, limite=3)
        assert r["total_analizadas"] == 3


def test_timestamp_presente(db_session):
    r = retro_aplicar(db_session, dry_run=True)
    assert "timestamp" in r
