"""Auditoría jun-2026 P2 #10: índices para los caminos calientes de
historial — creado_en (orden de /historial), factura (responder por
factura) y workflow_state (tablero de workflow).

Dos mecanismos que deben converger con los MISMOS nombres:
  - GlosaRecord.__table_args__ → DBs nuevas vía create_all().
  - _INDICES_HISTORIAL en app/main.py → DBs pre-existentes vía
    CREATE INDEX IF NOT EXISTS en el lifespan.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord  # noqa: F401 — registra historial en Base.metadata

INDICES_ESPERADOS = {
    "ix_historial_creado_en": ["creado_en"],
    "ix_historial_factura": ["factura"],
    "ix_historial_workflow_state": ["workflow_state"],
}


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    try:
        yield eng
    finally:
        eng.dispose()


def _indices_de_historial(engine) -> dict[str, list[str]]:
    return {ix["name"]: list(ix["column_names"]) for ix in inspect(engine).get_indexes("historial")}


class TestIndicesEnModelo:
    def test_create_all_crea_los_indices(self, engine):
        """DB nueva: create_all() debe dejar los 3 índices declarados
        en GlosaRecord.__table_args__."""
        Base.metadata.create_all(bind=engine)
        indices = _indices_de_historial(engine)
        for nombre, columnas in INDICES_ESPERADOS.items():
            assert nombre in indices, f"falta índice {nombre} (hay: {sorted(indices)})"
            assert indices[nombre] == columnas


class TestIndicesLifespanIdempotentes:
    def test_ddl_del_lifespan_repone_indices_en_tabla_preexistente(self, engine):
        """DB pre-existente SIN los índices (simulada borrándolos): el
        mismo DDL que corre el lifespan debe crearlos."""
        from app.main import _INDICES_HISTORIAL

        # El constante del lifespan debe cubrir exactamente los esperados
        assert {n: [c] for n, c in _INDICES_HISTORIAL} == INDICES_ESPERADOS

        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            for nombre in INDICES_ESPERADOS:
                db.execute(text(f"DROP INDEX {nombre}"))
            db.commit()
            assert not (set(INDICES_ESPERADOS) & set(_indices_de_historial(engine)))

            # Mismo loop que el lifespan (app/main.py)
            for _ix_nombre, _ix_col in _INDICES_HISTORIAL:
                db.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {_ix_nombre} ON historial ({_ix_col})")
                )
                db.commit()
        finally:
            db.close()

        indices = _indices_de_historial(engine)
        for nombre, columnas in INDICES_ESPERADOS.items():
            assert nombre in indices
            assert indices[nombre] == columnas

    def test_ddl_es_idempotente_sobre_db_ya_indexada(self, engine):
        """Correr el DDL del lifespan sobre una DB que YA tiene los índices
        (creados por create_all) no debe fallar — es el caso de cada boot."""
        from app.main import _INDICES_HISTORIAL

        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            for _ in range(2):  # dos boots seguidos
                for _ix_nombre, _ix_col in _INDICES_HISTORIAL:
                    db.execute(
                        text(f"CREATE INDEX IF NOT EXISTS {_ix_nombre} ON historial ({_ix_col})")
                    )
                    db.commit()
        finally:
            db.close()

        assert set(INDICES_ESPERADOS) <= set(_indices_de_historial(engine))
