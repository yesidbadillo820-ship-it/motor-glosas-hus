"""Tests del endpoint Control Center (Ronda 23).

Testing indirecto via las funciones que lo componen — el router requiere
auth + DB real, que ya está cubierto en otros tests de endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.api.routers.control_center import (
    _estado_scheduler_digest,
    _estado_scheduler_ia,
)
from app.services.autopilot_service import evaluar_bandeja
from app.services.digest_ejecutivo import generar_digest
from app.services.health_monitor import checar_salud


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


class TestComponentes:
    def test_scheduler_ia_devuelve_dict(self):
        e = _estado_scheduler_ia()
        assert isinstance(e, dict)

    def test_scheduler_digest_devuelve_dict(self):
        e = _estado_scheduler_digest()
        assert isinstance(e, dict)


class TestFlujoCompleto:
    """Simula lo que hace el endpoint /control-center/resumen sin pasar por FastAPI."""

    def test_resumen_integra_todas_las_partes(self, db_session):
        # Sembrar una glosa PENDIENTE para que la bandeja tenga algo
        g = GlosaRecord(
            eps="FAMISANAR EPS", paciente="X", factura="F-1",
            codigo_glosa="TA0201", valor_objetado=100_000,
            estado="PENDIENTE", creado_en=datetime.now(timezone.utc),
            dictamen="<p>Ley 1438/2011 Art 57. Resolución 2284/2023.</p>" * 20,
        )
        db_session.add(g)
        db_session.commit()

        salud = checar_salud(db_session)
        bandeja = evaluar_bandeja(db_session, auditor_email=None, limite=20)
        digest = generar_digest(db_session, periodo="dia")

        # Sanity checks de estructura
        assert "estado_general" in salud
        assert "componentes" in salud
        assert "total_evaluadas" in bandeja
        assert bandeja["total_evaluadas"] == 1
        assert "indicadores" in digest
        assert digest["indicadores"]["radicadas"] == 1

    def test_resumen_con_db_vacia_no_revienta(self, db_session):
        salud = checar_salud(db_session)
        bandeja = evaluar_bandeja(db_session, auditor_email=None, limite=20)
        digest = generar_digest(db_session, periodo="dia")
        assert salud["estado_general"] in ("OK", "ATENCION", "CRITICO")
        assert bandeja["total_evaluadas"] == 0
        assert digest["indicadores"]["radicadas"] == 0
