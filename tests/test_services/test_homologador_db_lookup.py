"""Tests del homologador_cups.homologar_cups con BD seedeada (R74 P2).

Garantizan el camino #3 del homologador: lookup en BD por
TarifaContratadaRecord.codigo_ips. Hasta ahora el módulo tenía tests
de tabla explícita y normalización heurística, pero el branch BD
(que se activa con cada Excel cargado por el coordinador) tenía
cobertura limitada.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import TarifaContratadaRecord
from app.services.homologador_cups import homologar_cups


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def _seed(db, **kw):
    base = dict(
        eps="FAMISANAR", codigo_cups="890750", codigo_ips=None,
        descripcion="X", valor_pactado=100_000,
        modalidad="TARIFA PROPIA", activa=1,
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(TarifaContratadaRecord(**base))
    db.commit()


class TestLookupBd:
    def test_codigo_ips_match_devuelve_cups_oficial(self, db):
        """Si el coordinador cargó el Excel con codigo_ips='39999X-99' y
        codigo_cups='890999', el homologador debe traducir."""
        _seed(db, codigo_ips="39999X-99", codigo_cups="890999",
              descripcion="PROCEDIMIENTO X")
        r = homologar_cups("39999X-99", db=db)
        assert r is not None
        assert r["cups_oficial"] == "890999"
        assert "PROCEDIMIENTO X" in r["descripcion"]

    def test_codigo_ips_inactivo_se_ignora(self, db):
        """activa=0 debe excluirse del lookup."""
        _seed(db, codigo_ips="OBSOLETO", codigo_cups="999000", activa=0)
        r = homologar_cups("OBSOLETO", db=db)
        # No debe matchear el inactivo (puede caer a normalización
        # heurística pero no a tabla BD)
        assert r is None or "contrato" not in r.get("fuente", "").lower()

    def test_filtro_eps_restringe(self, db):
        """Misma codigo_ips en 2 EPSs — el filtro eps debe restringir."""
        _seed(db, codigo_ips="DUAL", codigo_cups="111111", eps="EPS_A")
        _seed(db, codigo_ips="DUAL", codigo_cups="222222", eps="EPS_B")
        a = homologar_cups("DUAL", db=db, eps="EPS_A")
        b = homologar_cups("DUAL", db=db, eps="EPS_B")
        assert a is not None and a["cups_oficial"] == "111111"
        assert b is not None and b["cups_oficial"] == "222222"

    def test_codigo_oficial_no_pasa_por_lookup(self, db):
        """Si entrada YA es 6 dígitos (CUPS oficial), retorna directo
        sin tocar BD."""
        _seed(db, codigo_ips="OTRO_X", codigo_cups="890999")
        # Pasamos directamente el CUPS oficial 6-dígitos
        r = homologar_cups("123456", db=db)
        # Debe retornar 123456 directamente (camino 1, no consulta BD)
        assert r["cups_oficial"] == "123456"
        assert "oficial" in r["fuente"].lower()

    def test_sin_db_no_lookup_externa(self, db):
        """Sin db arg, no consulta BD; cae a normalización."""
        # Aun con tarifa seedeada, sin pasar db no la usa
        _seed(db, codigo_ips="EXOTICO-Y", codigo_cups="888888")
        r = homologar_cups("EXOTICO-Y")  # sin db arg
        # Sin BD → no encuentra → None o normalización heurística
        assert r is None or r["cups_oficial"] != "888888"
