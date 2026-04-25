"""Tests del módulo de mantenimiento (R57 P1)."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import (
    AICacheRecord,
    AICallRecord,
    GlosaEliminadaRecord,
)
from app.services.mantenimiento import (
    ejecutar_mantenimiento_completo,
    purgar_ai_cache_viejo,
    purgar_ai_calls_viejos,
    purgar_papelera_caducada,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()


class TestPurgarAiCache:
    def test_dry_run_no_borra(self, db):
        db.add(AICacheRecord(
            clave="x" * 64, modelo="claude", respuesta="r" * 100,
            creado_en=ahora_utc() - timedelta(days=60),
        ))
        db.commit()
        stats = purgar_ai_cache_viejo(db, dias=30, dry_run=True)
        assert stats["obsoletas"] == 1
        assert stats["purgadas"] == 0  # dry_run no borra
        assert db.query(AICacheRecord).count() == 1  # sigue ahí

    def test_purga_real_elimina_obsoletas(self, db):
        # 1 vieja + 1 reciente
        db.add(AICacheRecord(
            clave="a" * 64, modelo="x", respuesta="vieja",
            creado_en=ahora_utc() - timedelta(days=60),
        ))
        db.add(AICacheRecord(
            clave="b" * 64, modelo="x", respuesta="reciente",
            creado_en=ahora_utc() - timedelta(days=5),
        ))
        db.commit()
        stats = purgar_ai_cache_viejo(db, dias=30)
        assert stats["purgadas"] == 1
        assert db.query(AICacheRecord).count() == 1
        # La que sobrevive es la reciente
        sobrevivientes = db.query(AICacheRecord).all()
        assert sobrevivientes[0].respuesta == "reciente"

    def test_sin_obsoletas_es_noop(self, db):
        db.add(AICacheRecord(
            clave="x" * 64, modelo="x", respuesta="r",
            creado_en=ahora_utc(),
        ))
        db.commit()
        stats = purgar_ai_cache_viejo(db, dias=30)
        assert stats["purgadas"] == 0


class TestPurgarAiCalls:
    def test_purga_calls_viejos(self, db):
        db.add(AICallRecord(
            proveedor="anthropic", modelo="claude-sonnet-4-6", cost_usd=0.01,
            creado_en=ahora_utc() - timedelta(days=120),
        ))
        db.add(AICallRecord(
            proveedor="anthropic", modelo="claude-sonnet-4-6", cost_usd=0.01,
            creado_en=ahora_utc() - timedelta(days=10),
        ))
        db.commit()
        stats = purgar_ai_calls_viejos(db, dias=90)
        assert stats["obsoletas"] == 1
        assert stats["purgadas"] == 1
        assert db.query(AICallRecord).count() == 1


class TestPurgarPapelera:
    def test_purga_glosas_eliminadas_caducadas(self, db):
        # 1 caducada (>30d) + 1 reciente
        db.add(GlosaEliminadaRecord(
            glosa_id_original=1,
            snapshot_json=json.dumps({"eps": "X"}),
            eliminado_por="x@hus.com",
            eliminado_en=ahora_utc() - timedelta(days=40),
        ))
        db.add(GlosaEliminadaRecord(
            glosa_id_original=2,
            snapshot_json=json.dumps({"eps": "Y"}),
            eliminado_por="x@hus.com",
            eliminado_en=ahora_utc() - timedelta(days=10),
        ))
        db.commit()
        stats = purgar_papelera_caducada(db, dias=30)
        assert stats["purgadas"] == 1
        assert db.query(GlosaEliminadaRecord).count() == 1


class TestEjecutarMantenimientoCompleto:
    def test_ejecuta_las_3_purgas(self, db):
        # Agregamos 1 fila vieja en cada tabla
        db.add(AICacheRecord(clave="z" * 64, modelo="x", respuesta="r",
                              creado_en=ahora_utc() - timedelta(days=60)))
        db.add(AICallRecord(proveedor="anthropic", modelo="x", cost_usd=0.01,
                             creado_en=ahora_utc() - timedelta(days=120)))
        db.add(GlosaEliminadaRecord(
            glosa_id_original=99,
            snapshot_json="{}",
            eliminado_por="x@hus.com",
            eliminado_en=ahora_utc() - timedelta(days=40),
        ))
        db.commit()

        stats = ejecutar_mantenimiento_completo(db)
        assert stats["ai_cache"]["purgadas"] == 1
        assert stats["ai_calls"]["purgadas"] == 1
        assert stats["papelera"]["purgadas"] == 1
        assert "ejecutado_en" in stats
