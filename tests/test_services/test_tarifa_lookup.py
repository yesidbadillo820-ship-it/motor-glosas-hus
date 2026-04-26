"""Tests del tarifa_lookup_service (R72 P2)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import TarifaContratadaRecord
from app.services.tarifa_lookup_service import (
    calcular_valor_pactado,
    evaluar_glosa_tarifa,
    formato_texto_banner,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def _seed_tarifa(db, **kw):
    base = dict(
        eps="FAMISANAR", codigo_cups="890750",
        descripcion="CONSULTA URGENCIAS",
        valor_pactado=114_900,
        modalidad="TARIFA PROPIA", activa=1,
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(TarifaContratadaRecord(**base))
    db.commit()


class TestEvaluarGlosaTarifa:
    def test_sin_tarifa_retorna_no_encontrada(self, db):
        r = evaluar_glosa_tarifa(
            db, eps="FAMISANAR", cups="999999",
            valor_facturado=100_000, valor_objetado=50_000,
        )
        assert r["encontrada"] is False

    def test_match_perfecto_facturado_igual_pactado(self, db):
        """Cuando facturado == pactado, defender total."""
        _seed_tarifa(db, valor_pactado=114_900)
        r = evaluar_glosa_tarifa(
            db, eps="FAMISANAR", cups="890750",
            valor_facturado=114_900, valor_objetado=14_900,
            valor_reconocido=100_000,
        )
        assert r["encontrada"] is True
        assert r["tarifa"]["valor_pactado"] == 114_900

    def test_calcular_valor_pactado_sin_factor(self, db):
        """Para TARIFA PROPIA, valor_pactado es directo."""
        _seed_tarifa(db, valor_pactado=200_000, modalidad="TARIFA PROPIA")
        tarifa = db.query(TarifaContratadaRecord).first()
        v = calcular_valor_pactado(tarifa, valor_soat_base=500_000)
        assert v == 200_000


class TestFormatoBanner:
    def test_no_explota_con_dict_minimal(self):
        info = {"encontrada": False}
        out = formato_texto_banner(info)
        assert isinstance(out, str)

    def test_con_tarifa_genera_texto(self):
        info = {
            "encontrada": True,
            "tarifa": {
                "codigo_cups": "890750",
                "descripcion": "CONSULTA URGENCIAS",
                "valor_pactado": 114_900,
                "modalidad": "TARIFA PROPIA",
                "contrato_numero": "X",
            },
            "valor_facturado": 114_900,
            "valor_objetado": 14_900,
            "valor_reconocido": 100_000,
            "valor_pactado_calc": 114_900,
            "recomendacion": {
                "accion": "DEFENDER_TOTAL",
                "titulo": "ok",
                "razon": "ok",
            },
        }
        out = formato_texto_banner(info)
        assert "890750" in out
        assert "CONSULTA URGENCIAS" in out
