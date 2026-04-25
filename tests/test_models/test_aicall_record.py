"""Tests del modelo AICallRecord (R55 P5).

Garantiza:
  - defaults sensatos cuando se omiten campos opcionales
  - índices correctamente declarados (rendimiento de /sistema/metricas-ia)
  - persistencia + recuperación funciona
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import AICallRecord


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


class TestAICallRecordSchema:
    def test_tablename_correcto(self):
        assert AICallRecord.__tablename__ == "ai_calls"

    def test_columnas_obligatorias(self):
        insp = inspect(AICallRecord)
        cols = {c.key for c in insp.columns}
        # Todos los campos del helper de logging deben tener columna
        assert {
            "id", "proveedor", "modelo", "latency_ms",
            "input_tokens", "cache_creation_input_tokens",
            "cache_read_input_tokens", "output_tokens",
            "cost_usd", "glosa_id", "user_email", "creado_en",
        }.issubset(cols)

    def test_indices_declarados(self):
        """ix_aicalls_proveedor_creado debe existir para acelerar queries
        del endpoint de métricas filtradas por proveedor + ventana."""
        idx_names = {idx.name for idx in AICallRecord.__table__.indexes}
        assert "ix_aicalls_proveedor_creado" in idx_names
        # creado_en también debe estar indexado (Column(index=True))
        # Eso crea un índice automático ix_ai_calls_creado_en o similar.
        # Verificamos que la columna esté marcada como indexable.
        col_creado = AICallRecord.__table__.c.creado_en
        assert col_creado.index is True

    def test_glosa_id_es_nullable(self):
        """glosa_id es opcional — un call al LLM puede no estar atado a
        una glosa específica (ej. tests, healthchecks)."""
        cols = {c.key: c for c in inspect(AICallRecord).columns}
        assert cols["glosa_id"].nullable is True


class TestAICallRecordPersistencia:
    def test_persiste_y_recupera_call_minimal(self, db):
        """Crear con solo campos obligatorios — los nullable y defaults
        no deben fallar."""
        rec = AICallRecord(
            proveedor="anthropic", modelo="claude-sonnet-4-6",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        assert rec.id is not None
        # Defaults numéricos
        assert rec.latency_ms == 0
        assert rec.input_tokens == 0
        assert rec.cache_read_input_tokens == 0
        assert rec.cost_usd == 0.0
        # Nullables vacíos
        assert rec.glosa_id is None
        assert rec.user_email is None
        # creado_en con server_default
        assert rec.creado_en is not None

    def test_persiste_call_completo(self, db):
        rec = AICallRecord(
            proveedor="anthropic", modelo="claude-sonnet-4-6",
            latency_ms=1234,
            input_tokens=100, cache_creation_input_tokens=8000,
            cache_read_input_tokens=0, output_tokens=500,
            cost_usd=0.0345,
            glosa_id=42,
            user_email="auditor@hus.com",
        )
        db.add(rec)
        db.commit()
        # Recuperar y validar
        recuperado = db.query(AICallRecord).filter_by(glosa_id=42).first()
        assert recuperado is not None
        assert recuperado.modelo == "claude-sonnet-4-6"
        assert recuperado.cost_usd == 0.0345
        assert recuperado.user_email == "auditor@hus.com"

    def test_indice_creado_en_acelera_query(self, db):
        """No es benchmark — solo verifica que la query con filtro
        creado_en > X funcione (aprovechando el índice declarado)."""
        for i in range(5):
            db.add(AICallRecord(
                proveedor="anthropic", modelo="claude-sonnet-4-6",
                latency_ms=i * 100, cost_usd=i * 0.001,
            ))
        db.commit()
        # Query con filtro
        from datetime import timedelta
        desde = ahora_utc() - timedelta(hours=1)
        cnt = db.query(AICallRecord).filter(AICallRecord.creado_en >= desde).count()
        assert cnt == 5

    def test_multiples_proveedores(self, db):
        """proveedor distingue anthropic vs groq — útil para desglose."""
        db.add(AICallRecord(proveedor="anthropic", modelo="claude-sonnet-4-6", cost_usd=0.05))
        db.add(AICallRecord(proveedor="groq", modelo="llama-3.3-70b-versatile", cost_usd=0.001))
        db.commit()
        antrhopic = db.query(AICallRecord).filter_by(proveedor="anthropic").count()
        groq = db.query(AICallRecord).filter_by(proveedor="groq").count()
        assert antrhopic == 1
        assert groq == 1
