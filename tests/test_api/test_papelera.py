"""Tests del router /papelera (R52 P3 — fix datetime TZ-aware bug)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaEliminadaRecord


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


def _seed(db, eliminado_en, snap=None):
    snap = snap or {"eps": "FAMISANAR", "factura": "FE-1", "codigo_glosa": "TA0201"}
    reg = GlosaEliminadaRecord(
        glosa_id_original=1,
        snapshot_json=json.dumps(snap),
        eliminado_por="test@hus.com",
        eliminado_en=eliminado_en,
        motivo="test",
    )
    db.add(reg)
    db.commit()
    return reg


class TestPapeleraListar:
    def test_listar_con_eliminado_en_tz_aware(self, db):
        """Caso normal: eliminado_en TZ-aware (como en Postgres)."""
        from app.api.routers.papelera import listar
        _seed(db, datetime.now(timezone.utc) - timedelta(days=2))
        user = MagicMock(email="admin@hus.com", rol="ADMIN")
        items = listar(db=db, current_user=user)
        assert len(items) == 1
        assert items[0]["dias_restantes_restaurar"] == 28
        assert items[0]["eps"] == "FAMISANAR"

    def test_listar_con_eliminado_en_naive_no_explota(self, db):
        """REGRESIÓN: registro con eliminado_en naive no debe lanzar
        TypeError 'can't subtract offset-naive and offset-aware datetimes'.
        Antes del fix, esto era un 500 en producción cuando algunos
        registros tenían naive y otros tz-aware."""
        from app.api.routers.papelera import listar
        _seed(db, datetime.utcnow() - timedelta(days=5))  # naive
        user = MagicMock(email="admin@hus.com", rol="ADMIN")
        items = listar(db=db, current_user=user)
        assert len(items) == 1
        assert items[0]["dias_restantes_restaurar"] == 25
        # eliminado_en debe estar normalizado (con timezone)
        assert items[0]["eliminado_en"] is not None

    def test_listar_excluye_mas_de_30_dias(self, db):
        """Registros >30 días no se listan (caducaron para restauración)."""
        from app.api.routers.papelera import listar
        _seed(db, datetime.now(timezone.utc) - timedelta(days=35))
        _seed(db, datetime.now(timezone.utc) - timedelta(days=2))
        user = MagicMock(email="admin@hus.com", rol="ADMIN")
        items = listar(db=db, current_user=user)
        assert len(items) == 1
        assert items[0]["dias_restantes_restaurar"] == 28

    def test_listar_vacia(self, db):
        from app.api.routers.papelera import listar
        user = MagicMock(email="admin@hus.com", rol="ADMIN")
        assert listar(db=db, current_user=user) == []


class TestHelperTz:
    def test_normalizar_naive_agrega_utc(self):
        from app.api.routers.papelera import _normalizar_tz
        naive = datetime(2026, 4, 25, 10, 0)
        out = _normalizar_tz(naive)
        assert out.tzinfo is not None
        assert out.tzinfo == timezone.utc

    def test_normalizar_tz_aware_no_modifica(self):
        from app.api.routers.papelera import _normalizar_tz
        aware = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
        out = _normalizar_tz(aware)
        assert out == aware

    def test_normalizar_none(self):
        from app.api.routers.papelera import _normalizar_tz
        assert _normalizar_tz(None) is None
