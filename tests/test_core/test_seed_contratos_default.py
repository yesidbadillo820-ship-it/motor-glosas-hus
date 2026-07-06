"""Regresión auditoría jun-2026 P1 #4: el seed de contratos del lifespan
sobrescribía `detalles` de las 14 EPS default en CADA arranque (revirtiendo
las ediciones hechas por la coordinación desde la UI) y borraba cualquier
contrato cuyo EPS no estuviera en CONTRATOS_DEFAULT (perdiendo contratos
creados por el equipo).

Contrato nuevo de _sembrar_contratos_default:
  - Siembra SOLO los que faltan; la BD es la fuente de verdad.
  - FORCE_RESEED_CONTRATOS=1 restaura la re-sincronización masiva.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import ContratoRecord


@pytest.fixture
def db_session():
    """Sesión sqlite en memoria, aislada del resto de la suite."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db, **kwargs):
    from app.main import _sembrar_contratos_default

    _sembrar_contratos_default(db, **kwargs)
    db.commit()


class TestSeedContratosNoRevierteEdiciones:
    def test_db_vacia_siembra_todos_los_default(self, db_session):
        from app.main import CONTRATOS_DEFAULT

        _seed(db_session)
        eps_en_db = {c.eps for c in db_session.query(ContratoRecord).all()}
        assert eps_en_db == set(CONTRATOS_DEFAULT.keys())

    def test_edicion_de_coordinacion_sobrevive_reboot(self, db_session):
        """El caso del bug: un coordinador edita el texto de FAMISANAR
        desde la UI; el siguiente deploy NO debe revertirlo."""
        _seed(db_session)

        contrato = (
            db_session.query(ContratoRecord).filter(ContratoRecord.eps == "FAMISANAR EPS").first()
        )
        contrato.detalles = "CONTRATO RENEGOCIADO 2026 — TARIFA SOAT -8% (editado por coordinación)"
        db_session.commit()

        _seed(db_session)  # simula el siguiente arranque

        contrato = (
            db_session.query(ContratoRecord).filter(ContratoRecord.eps == "FAMISANAR EPS").first()
        )
        assert "editado por coordinación" in contrato.detalles

    def test_contrato_creado_por_ui_sobrevive_reboot(self, db_session):
        """Contratos de EPS que NO están en CONTRATOS_DEFAULT (creados vía
        POST /contratos) no deben borrarse en el arranque."""
        _seed(db_session)
        db_session.add(ContratoRecord(eps="EPS NUEVA REGIONAL", detalles="CONTRATO 2026 SOAT -12%"))
        db_session.commit()

        _seed(db_session)  # simula el siguiente arranque

        assert (
            db_session.query(ContratoRecord)
            .filter(ContratoRecord.eps == "EPS NUEVA REGIONAL")
            .first()
            is not None
        )

    def test_default_faltante_se_resiembra(self, db_session):
        """Si alguien borra un default, el siguiente arranque lo repone."""
        from app.main import CONTRATOS_DEFAULT

        _seed(db_session)
        borrado = db_session.query(ContratoRecord).filter(ContratoRecord.eps == "COOSALUD").first()
        db_session.delete(borrado)
        db_session.commit()

        _seed(db_session)

        repuesto = db_session.query(ContratoRecord).filter(ContratoRecord.eps == "COOSALUD").first()
        assert repuesto is not None
        assert repuesto.detalles == CONTRATOS_DEFAULT["COOSALUD"]


class TestForceReseedContratos:
    def test_force_reseed_resincroniza_textos(self, db_session):
        from app.main import CONTRATOS_DEFAULT

        _seed(db_session)
        contrato = (
            db_session.query(ContratoRecord).filter(ContratoRecord.eps == "FAMISANAR EPS").first()
        )
        contrato.detalles = "TEXTO EDITADO"
        db_session.commit()

        _seed(db_session, force_reseed=True)

        contrato = (
            db_session.query(ContratoRecord).filter(ContratoRecord.eps == "FAMISANAR EPS").first()
        )
        assert contrato.detalles == CONTRATOS_DEFAULT["FAMISANAR EPS"]

    def test_force_reseed_elimina_no_default(self, db_session):
        _seed(db_session)
        db_session.add(ContratoRecord(eps="EPS OBSOLETA", detalles="X"))
        db_session.commit()

        _seed(db_session, force_reseed=True)

        assert (
            db_session.query(ContratoRecord).filter(ContratoRecord.eps == "EPS OBSOLETA").first()
            is None
        )
