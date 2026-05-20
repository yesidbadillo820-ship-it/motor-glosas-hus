"""Tests para obtener_few_shot() — incluyendo fallback por familia GENERICO."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import PlantillaGoldRecord


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _agregar(db, eps, codigo, titulo, argumento, usos=0):
    rec = PlantillaGoldRecord(
        eps=eps,
        codigo_glosa=codigo,
        titulo=titulo,
        argumento=argumento,
        activa=1,
        usos=usos,
        tipo="PLANTILLA_HUS_BASE" if eps == "GENERICO" else None,
        creado_por="test",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


ARG = "x" * 100


class TestObtenerFewShot:
    def test_match_exacto_prevalece(self, db):
        from app.api.routers.plantillas_gold import obtener_few_shot

        _agregar(db, "FAMISANAR", "TA0201", "T exacto", ARG + "EX", usos=10)
        _agregar(db, "GENERICO", "TA-G01", "T generico", ARG + "GEN", usos=99)

        resultado = obtener_few_shot(db, "FAMISANAR", "TA0201", limite=1)
        assert len(resultado) == 1
        assert resultado[0].eps == "FAMISANAR"
        assert resultado[0].codigo_glosa == "TA0201"

    def test_fallback_mismo_codigo_otras_eps(self, db):
        from app.api.routers.plantillas_gold import obtener_few_shot

        _agregar(db, "NUEVA EPS", "TA0201", "T otra EPS", ARG + "NE", usos=5)
        _agregar(db, "GENERICO", "TA-G01", "T generico", ARG + "GEN", usos=2)

        resultado = obtener_few_shot(db, "FAMISANAR", "TA0201", limite=1)
        assert len(resultado) == 1
        assert resultado[0].eps == "NUEVA EPS"

    def test_fallback_familia_generico(self, db):
        from app.api.routers.plantillas_gold import obtener_few_shot

        _agregar(db, "GENERICO", "TA-G01", "T TA-G01", ARG + "G01", usos=3)
        _agregar(db, "GENERICO", "TA-G02", "T TA-G02", ARG + "G02", usos=1)
        _agregar(db, "GENERICO", "SO-G01", "T SO-G01", ARG + "SO1", usos=9)

        # Sin plantilla exacta ni mismo código → debe caer en TA-G*
        resultado = obtener_few_shot(db, "FAMISANAR", "TA0201", limite=2)
        assert len(resultado) == 2
        codigos = {r.codigo_glosa for r in resultado}
        assert codigos.issubset({"TA-G01", "TA-G02"})

    def test_fallback_familia_no_mezcla_grupos(self, db):
        from app.api.routers.plantillas_gold import obtener_few_shot

        _agregar(db, "GENERICO", "SO-G01", "T SO-G01", ARG + "SO1", usos=9)
        _agregar(db, "GENERICO", "TA-G01", "T TA-G01", ARG + "TA1", usos=1)

        resultado = obtener_few_shot(db, "FAMISANAR", "SO0501", limite=1)
        assert len(resultado) == 1
        assert resultado[0].codigo_glosa == "SO-G01"

    def test_sin_plantillas_devuelve_vacia(self, db):
        from app.api.routers.plantillas_gold import obtener_few_shot

        resultado = obtener_few_shot(db, "FAMISANAR", "TA0201")
        assert resultado == []

    def test_codigo_vacio_devuelve_vacia(self, db):
        from app.api.routers.plantillas_gold import obtener_few_shot

        assert obtener_few_shot(db, "FAMISANAR", "") == []
        assert obtener_few_shot(db, "FAMISANAR", None) == []
