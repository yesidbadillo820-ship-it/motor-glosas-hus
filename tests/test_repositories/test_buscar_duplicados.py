"""Tests del detector de duplicados de factura (R58 P1)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import GlosaRecord
from app.repositories.glosa_repository import buscar_duplicados_factura


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


def _seed(db, **kw):
    base = dict(
        eps="FAMISANAR", paciente="X",
        codigo_glosa="TA0201", valor_objetado=10_000,
        factura="FE-001", creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestBuscarDuplicadosFactura:
    def test_factura_inexistente(self, db):
        assert buscar_duplicados_factura(db, "FE-NO-EXISTE") == []

    def test_factura_vacia_o_corta_retorna_vacio(self, db):
        """No debe matchear nada con inputs ambiguos como 'N/A' o ''."""
        _seed(db, factura="N/A")
        assert buscar_duplicados_factura(db, "") == []
        assert buscar_duplicados_factura(db, "X") == []
        assert buscar_duplicados_factura(db, None) == []

    def test_match_exacto_devuelve_glosa(self, db):
        _seed(db, factura="FE-2026-001", eps="FAMISANAR")
        r = buscar_duplicados_factura(db, "FE-2026-001")
        assert len(r) == 1
        assert r[0].factura == "FE-2026-001"

    def test_case_insensitive_y_trim(self, db):
        _seed(db, factura="FE-2026-002", eps="FAMISANAR")
        # Match con espacios y minúsculas
        r = buscar_duplicados_factura(db, "  fe-2026-002  ")
        assert len(r) == 1

    def test_filtro_por_eps(self, db):
        """Misma factura pero diferentes EPS — el filtro EPS debe restringir."""
        _seed(db, factura="FE-X", eps="FAMISANAR")
        _seed(db, factura="FE-X", eps="SALUD TOTAL")
        r_fami = buscar_duplicados_factura(db, "FE-X", eps="FAMISANAR")
        r_st = buscar_duplicados_factura(db, "FE-X", eps="SALUD TOTAL")
        r_all = buscar_duplicados_factura(db, "FE-X")
        assert len(r_fami) == 1
        assert r_fami[0].eps == "FAMISANAR"
        assert len(r_st) == 1
        assert r_st[0].eps == "SALUD TOTAL"
        assert len(r_all) == 2

    def test_orden_por_fecha_desc(self, db):
        from datetime import timedelta
        antiguo = ahora_utc() - timedelta(days=10)
        reciente = ahora_utc()
        _seed(db, factura="FE-DUP", creado_en=antiguo)
        _seed(db, factura="FE-DUP", creado_en=reciente)
        r = buscar_duplicados_factura(db, "FE-DUP")
        assert len(r) == 2
        # Más reciente primero
        assert r[0].creado_en >= r[1].creado_en

    def test_respeta_limite(self, db):
        for i in range(8):
            _seed(db, factura="FE-LIM")
        r = buscar_duplicados_factura(db, "FE-LIM", limite=3)
        assert len(r) == 3
