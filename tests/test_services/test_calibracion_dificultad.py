"""Tests de calibración por dificultad histórica (R-cerebro #3)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import GlosaRecord
from app.services.calibracion_dificultad import (
    bloque_calibracion_para_prompt,
    calcular_dificultad,
    construir_bloque_calibracion,
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


def _seed(db, eps, codigo, estado):
    db.add(GlosaRecord(
        eps=eps, paciente="X", codigo_glosa=codigo,
        valor_objetado=1000, etapa="X", estado=estado,
        creado_en=ahora_utc(),
    ))
    db.commit()


class TestCalcularDificultad:
    def test_sin_db(self):
        assert calcular_dificultad(None, "X", "C") is None

    def test_pocas_muestras(self, db):
        _seed(db, "X", "C", "LEVANTADA")
        _seed(db, "X", "C", "LEVANTADA")
        # Solo 2 muestras < 3 → None
        assert calcular_dificultad(db, "X", "C") is None

    def test_caso_favorable(self, db):
        # 4/4 LEV → 100%
        for _ in range(4):
            _seed(db, "X", "C", "LEVANTADA")
        d = calcular_dificultad(db, "X", "C")
        assert d is not None
        assert d["nivel"] == "FAVORABLE"
        assert d["tasa_pct"] == 100.0

    def test_caso_dificil(self, db):
        # 0/4 LEV → 0%
        for _ in range(4):
            _seed(db, "X", "C", "RATIFICADA")
        d = calcular_dificultad(db, "X", "C")
        assert d is not None
        assert d["nivel"] == "DIFICIL"

    def test_caso_medio(self, db):
        # 2 LEV / 3 RAT = 40%
        for _ in range(2):
            _seed(db, "X", "C", "LEVANTADA")
        for _ in range(3):
            _seed(db, "X", "C", "RATIFICADA")
        d = calcular_dificultad(db, "X", "C")
        assert d is not None
        assert d["nivel"] == "MEDIO"


class TestBloque:
    def test_none_devuelve_vacio(self):
        assert bloque_calibracion_para_prompt(None) == ""

    def test_favorable_dice_favorable(self):
        b = bloque_calibracion_para_prompt({
            "nivel": "FAVORABLE", "tasa_pct": 80, "n_muestras": 5,
            "n_levantadas": 4,
        })
        assert "FAVORABLE" in b

    def test_dificil_pide_blindaje(self):
        b = bloque_calibracion_para_prompt({
            "nivel": "DIFICIL", "tasa_pct": 20, "n_muestras": 5,
            "n_levantadas": 1,
        })
        assert "BLINDAJE" in b
        assert "anti-rebatimiento" in b


class TestIntegrado:
    def test_un_paso_ok(self, db):
        for _ in range(5):
            _seed(db, "X", "C", "LEVANTADA")
        b = construir_bloque_calibracion(db, "X", "C")
        assert "FAVORABLE" in b

    def test_un_paso_sin_datos(self, db):
        assert construir_bloque_calibracion(db, "Z", "Z01") == ""
