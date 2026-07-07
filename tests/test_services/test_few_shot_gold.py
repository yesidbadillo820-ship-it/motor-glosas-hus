"""Tests del few-shot dinámico Gold (R-cerebro #2)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import GlosaRecord, PlantillaGoldRecord
from app.services.few_shot_gold import (
    bloque_few_shot_para_prompt,
    obtener_ejemplos_gold,
)


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


def _seed_glosa(db, eps, codigo, estado="LEVANTADA", dictamen=None):
    db.add(
        GlosaRecord(
            eps=eps,
            paciente="X",
            codigo_glosa=codigo,
            valor_objetado=1000,
            etapa="X",
            estado=estado,
            creado_en=ahora_utc(),
            dictamen=dictamen,
            fecha_decision_eps=ahora_utc(),
        )
    )
    db.commit()


def _seed_gold(db, eps, codigo, argumento, usos=10):
    db.add(
        PlantillaGoldRecord(
            eps=eps,
            codigo_glosa=codigo,
            argumento=argumento,
            activa=1,
            usos=usos,
        )
    )
    db.commit()


class TestObtenerEjemplos:
    def test_sin_db_devuelve_vacio(self):
        assert obtener_ejemplos_gold(None, "X", "C") == []

    def test_sin_eps_o_codigo(self, db):
        assert obtener_ejemplos_gold(db, "", "C") == []
        assert obtener_ejemplos_gold(db, "X", "") == []

    def test_prefiere_plantilla_gold(self, db):
        _seed_gold(db, "SAN", "TA01", "x" * 250, usos=20)
        _seed_glosa(db, "SAN", "TA01", "LEVANTADA", "y" * 250)
        ejs = obtener_ejemplos_gold(db, "SAN", "TA01", max_ejemplos=2)
        # La función devuelve "hasta N" ejemplos por prelación (banco HUS →
        # gold → histórico). Con max=2, 1 gold y 1 histórico, devuelve ambos
        # con el GOLD de primero (esa es la "preferencia" que valida el test).
        assert len(ejs) == 2
        assert ejs[0]["fuente"] == "GOLD"
        assert ejs[1]["fuente"] == "HISTORICO"

    def test_gold_unico_cuando_max_1(self, db):
        # Con max=1 y un gold disponible, el gold ocupa el único slot
        # (no se cuela el histórico).
        _seed_gold(db, "SAN", "TA01", "x" * 250, usos=20)
        _seed_glosa(db, "SAN", "TA01", "LEVANTADA", "y" * 250)
        ejs = obtener_ejemplos_gold(db, "SAN", "TA01", max_ejemplos=1)
        assert len(ejs) == 1
        assert ejs[0]["fuente"] == "GOLD"

    def test_fallback_a_historico(self, db):
        # Sin gold, hay glosa LEVANTADA
        _seed_glosa(db, "X", "C", "LEVANTADA", "x" * 250)
        ejs = obtener_ejemplos_gold(db, "X", "C")
        assert len(ejs) == 1
        assert ejs[0]["fuente"] == "HISTORICO"

    def test_dictamen_corto_descartado(self, db):
        # Dictamen <200 chars: no se cuenta
        _seed_glosa(db, "X", "C", "LEVANTADA", "muy corto")
        assert obtener_ejemplos_gold(db, "X", "C") == []

    def test_solo_estados_levantada(self, db):
        _seed_glosa(db, "X", "C", "RATIFICADA", "x" * 250)
        assert obtener_ejemplos_gold(db, "X", "C") == []


class TestBloque:
    def test_bloque_vacio_si_sin_ejemplos(self):
        assert bloque_few_shot_para_prompt([]) == ""

    def test_bloque_contiene_ejemplos(self):
        ejs = [
            {"argumento": "TEXTO 1 GANADOR", "fuente": "GOLD", "id": 1},
        ]
        b = bloque_few_shot_para_prompt(ejs)
        assert "TEXTO 1 GANADOR" in b
        assert "EJEMPLOS DE DICTÁMENES GANADORES" in b


