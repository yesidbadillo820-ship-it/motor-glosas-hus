"""Tests del health monitor (Ronda 17)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.services.health_monitor import (
    _peor_estado,
    _check_bd,
    _check_cache_ia,
    _check_glosas_hoy,
    _check_anomalias,
    _check_bots,
    _check_actividad_reciente,
    checar_salud,
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


# ─── _peor_estado ──────────────────────────────────────────────────────────

class TestPeorEstado:
    def test_todos_ok(self):
        assert _peor_estado(["OK", "OK", "OK"]) == "OK"

    def test_uno_critico_gana(self):
        assert _peor_estado(["OK", "ATENCION", "CRITICO"]) == "CRITICO"

    def test_atencion_si_hay_atencion(self):
        assert _peor_estado(["OK", "ATENCION"]) == "ATENCION"

    def test_lento_se_degrada_a_atencion(self):
        assert _peor_estado(["OK", "LENTO"]) == "ATENCION"

    def test_desconocido_degrada_a_atencion(self):
        assert _peor_estado(["OK", "DESCONOCIDO"]) == "ATENCION"

    def test_lista_vacia_devuelve_ok(self):
        assert _peor_estado([]) == "OK"


# ─── _check_bd ─────────────────────────────────────────────────────────────

class TestCheckBd:
    def test_bd_viva_retorna_ok(self, db_session):
        r = _check_bd(db_session)
        assert r["estado"] == "OK"
        assert isinstance(r["latencia_ms"], (int, float))
        assert r["latencia_ms"] < 500


# ─── _check_glosas_hoy ─────────────────────────────────────────────────────

class TestCheckGlosasHoy:
    def test_sin_glosas_ok(self, db_session):
        r = _check_glosas_hoy(db_session)
        assert r["estado"] == "OK"
        assert r["radicadas_hoy"] == 0
        assert r["vencidas"] == 0

    def test_vencidas_pocas_atencion(self, db_session):
        g = GlosaRecord(
            eps="X", estado="PENDIENTE", dias_restantes=-2,
            codigo_glosa="TA0201", valor_objetado=10000,
            creado_en=datetime.now(timezone.utc),
        )
        db_session.add(g)
        db_session.commit()
        r = _check_glosas_hoy(db_session)
        assert r["estado"] == "ATENCION"
        assert r["vencidas"] == 1

    def test_vencidas_muchas_critico(self, db_session):
        for i in range(12):
            db_session.add(GlosaRecord(
                eps="X", estado="PENDIENTE", dias_restantes=-1,
                codigo_glosa="TA0201", valor_objetado=1000,
                creado_en=datetime.now(timezone.utc),
            ))
        db_session.commit()
        r = _check_glosas_hoy(db_session)
        assert r["estado"] == "CRITICO"


# ─── _check_cache_ia ───────────────────────────────────────────────────────

class TestCheckCache:
    def test_sin_cache_ratio_cero(self, db_session):
        r = _check_cache_ia(db_session)
        assert r["estado"] == "OK"
        assert r["entradas"] == 0
        assert r["hits_acumulados"] == 0


# ─── _check_anomalias ──────────────────────────────────────────────────────

class TestCheckAnomalias:
    def test_sin_anomalias_ok(self, db_session):
        r = _check_anomalias(db_session)
        assert r["estado"] == "OK"
        assert r["duplicados"] == 0

    def test_con_duplicado_alta(self, db_session):
        # 3 glosas duplicadas → ALTA
        for _ in range(3):
            db_session.add(GlosaRecord(
                eps="X", factura="DUP-1", cups_servicio="999",
                estado="PENDIENTE", valor_objetado=1000,
                codigo_glosa="TA0201",
                creado_en=datetime.now(timezone.utc),
            ))
        db_session.commit()
        r = _check_anomalias(db_session)
        # Con 1 ALTA pasa a ATENCION (necesita ≥3 para CRITICO)
        assert r["estado"] == "ATENCION"
        assert r["alta"] == 1


# ─── _check_bots ───────────────────────────────────────────────────────────

class TestCheckBots:
    def test_sin_credenciales_degrada_a_mock(self, monkeypatch):
        monkeypatch.delenv("WHATSAPP_META_TOKEN", raising=False)
        monkeypatch.delenv("WHATSAPP_META_PHONE_ID", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        r = _check_bots()
        assert r["estado"] == "OK"
        assert r["providers_configurados"] == []
        assert r["fallback_activo"] == "mock"


# ─── _check_actividad_reciente ─────────────────────────────────────────────

class TestActividadReciente:
    def test_sin_actividad_ok(self, db_session):
        r = _check_actividad_reciente(db_session, horas=6)
        assert r["estado"] == "OK"
        assert r["eventos"] == 0


# ─── checar_salud consolidado ──────────────────────────────────────────────

class TestCheckSaludConsolidado:
    def test_sistema_vacio_retorna_ok(self, db_session):
        r = checar_salud(db_session)
        assert r["estado_general"] in ("OK", "ATENCION")  # scheduler puede estar inactivo en tests
        assert "componentes" in r
        assert "bd" in r["componentes"]
        assert "generado_en" in r
        assert isinstance(r["alertas"], list)

    def test_entorno_presente(self, db_session):
        r = checar_salud(db_session)
        assert "entorno" in r
        assert "env" in r["entorno"]

    def test_todos_los_componentes_presentes(self, db_session):
        r = checar_salud(db_session)
        esperados = {
            "bd", "scheduler_ia_proactiva", "cache_ia",
            "glosas_hoy", "anomalias", "bots", "actividad_reciente",
        }
        assert set(r["componentes"].keys()) == esperados
