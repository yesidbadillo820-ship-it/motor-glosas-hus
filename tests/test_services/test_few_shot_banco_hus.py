"""Tests para el fallback de banco HUS en obtener_ejemplos_gold + bloque dual."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord, PlantillaGoldRecord
from app.services.few_shot_gold import bloque_few_shot_para_prompt, obtener_ejemplos_gold


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


ARG_LARGO = "TEXTO JURÍDICO " * 30  # >200 chars


class TestObtenerEjemplosBancoHUS:
    def test_fallback_banco_hus_cuando_no_hay_gold_ni_historico(self, db):
        db.add(
            PlantillaGoldRecord(
                eps="GENERICO",
                codigo_glosa="TA-G01",
                titulo="Banco HUS TA-G01",
                argumento=ARG_LARGO,
                activa=1,
                tipo="PLANTILLA_HUS_BASE",
                usos=0,
            )
        )
        db.commit()

        ejemplos = obtener_ejemplos_gold(db, "FAMISANAR", "TA0201")
        assert len(ejemplos) == 1
        assert ejemplos[0]["fuente"] == "BANCO_HUS"

    def test_banco_hus_prevalece_sobre_gold_curado(self, db):
        """Revisión 21 mayo 2026 — Yesid: banco HUS tiene prelación absoluta.
        Sus citas están verificadas, las plantillas curadas custom no."""
        db.add(
            PlantillaGoldRecord(
                eps="FAMISANAR",
                codigo_glosa="TA0201",
                titulo="Gold exacto",
                argumento=ARG_LARGO + " EXACTO",
                activa=1,
                usos=10,
            )
        )
        db.add(
            PlantillaGoldRecord(
                eps="GENERICO",
                codigo_glosa="TA-G01",
                titulo="Banco HUS",
                argumento=ARG_LARGO,
                activa=1,
                tipo="PLANTILLA_HUS_BASE",
            )
        )
        db.commit()

        ejemplos = obtener_ejemplos_gold(db, "FAMISANAR", "TA0201")
        assert len(ejemplos) == 1
        assert ejemplos[0]["fuente"] == "BANCO_HUS"

    def test_banco_hus_prevalece_sobre_historico(self, db):
        """Banco HUS también gana al histórico — citas verificadas first."""
        from datetime import datetime, timezone

        db.add(
            GlosaRecord(
                eps="FAMISANAR",
                codigo_glosa="TA0201",
                estado="LEVANTADA",
                dictamen=ARG_LARGO + " HISTÓRICO",
                fecha_decision_eps=datetime.now(timezone.utc),
            )
        )
        db.add(
            PlantillaGoldRecord(
                eps="GENERICO",
                codigo_glosa="TA-G01",
                titulo="Banco HUS",
                argumento=ARG_LARGO,
                activa=1,
                tipo="PLANTILLA_HUS_BASE",
            )
        )
        db.commit()

        ejemplos = obtener_ejemplos_gold(db, "FAMISANAR", "TA0201")
        assert len(ejemplos) == 1
        assert ejemplos[0]["fuente"] == "BANCO_HUS"

    def test_sin_banco_hus_para_familia_usa_gold(self, db):
        """Si banco HUS NO tiene la familia (ej. XX-G*), cae al GOLD curado."""
        # Solo plantilla custom, NO banco HUS para XX-G*
        db.add(
            PlantillaGoldRecord(
                eps="FAMISANAR",
                codigo_glosa="XX0101",
                titulo="Gold para familia sin banco",
                argumento=ARG_LARGO + " GOLD-XX",
                activa=1,
                usos=5,
            )
        )
        db.commit()

        ejemplos = obtener_ejemplos_gold(db, "FAMISANAR", "XX0101")
        assert len(ejemplos) == 1
        assert ejemplos[0]["fuente"] == "GOLD"

    def test_gold_con_pocos_usos_descartado(self, db):
        """Plantillas curadas con usos < 3 ahora son descartadas (probable
        baja calidad / citas no verificadas)."""
        db.add(
            PlantillaGoldRecord(
                eps="FAMISANAR",
                codigo_glosa="XX0101",
                titulo="Gold nuevo sin uso",
                argumento=ARG_LARGO,
                activa=1,
                usos=1,  # < 3, debe descartarse
            )
        )
        db.commit()

        ejemplos = obtener_ejemplos_gold(db, "FAMISANAR", "XX0101")
        assert len(ejemplos) == 0

    def test_banco_hus_familia_correcta(self, db):
        # SO-G* no debe aparecer cuando se pide TA
        for cod in ["SO-G01", "SO-G02", "CL-G01"]:
            db.add(
                PlantillaGoldRecord(
                    eps="GENERICO",
                    codigo_glosa=cod,
                    titulo=cod,
                    argumento=ARG_LARGO,
                    activa=1,
                    tipo="PLANTILLA_HUS_BASE",
                )
            )
        db.add(
            PlantillaGoldRecord(
                eps="GENERICO",
                codigo_glosa="TA-G01",
                titulo="TA correcta",
                argumento=ARG_LARGO + " TA",
                activa=1,
                tipo="PLANTILLA_HUS_BASE",
            )
        )
        db.commit()

        ejemplos = obtener_ejemplos_gold(db, "FAMISANAR", "TA0201")
        assert len(ejemplos) == 1
        assert "TA" in ejemplos[0]["argumento"][-20:]


class TestBloqueFewShotDual:
    def test_bloque_banco_hus_usa_lenguaje_de_plantilla_base(self):
        ejemplos = [{"argumento": "TEXTO JURÍDICO HUS", "fuente": "BANCO_HUS", "id": 1}]
        bloque = bloque_few_shot_para_prompt(ejemplos)
        assert "PLANTILLA(S) JURÍDICA(S) BASE" in bloque
        assert "BANCO HUS" in bloque
        assert "ESQUELETO BASE" in bloque
        assert "NOMBRE DEL SERVICIO" in bloque
        assert "VALORES MONETARIOS" in bloque
        assert "PROHIBIDO inventar" in bloque

    def test_bloque_gold_usa_lenguaje_de_ejemplo(self):
        ejemplos = [{"argumento": "DICTAMEN GANADOR", "fuente": "GOLD", "id": 1}]
        bloque = bloque_few_shot_para_prompt(ejemplos)
        assert "EJEMPLOS DE DICTÁMENES GANADORES" in bloque
        assert "NO copies textualmente" in bloque
        assert "PLANTILLA(S) JURÍDICA(S) BASE" not in bloque

    def test_bloque_mixto_no_es_banco_hus(self):
        ejemplos = [
            {"argumento": "T1", "fuente": "GOLD", "id": 1},
            {"argumento": "T2", "fuente": "BANCO_HUS", "id": 2},
        ]
        bloque = bloque_few_shot_para_prompt(ejemplos)
        assert "EJEMPLOS DE DICTÁMENES GANADORES" in bloque
        assert "PLANTILLA(S) JURÍDICA(S) BASE" not in bloque

    def test_bloque_vacio_devuelve_string_vacio(self):
        assert bloque_few_shot_para_prompt([]) == ""
