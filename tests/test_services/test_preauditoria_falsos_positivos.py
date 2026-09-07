"""Los dos falsos positivos que sacó la primera factura real (04-09-2026).

Se probó la pre-auditoría contra `Rips_HUS559077.json` del share del hospital
—531 KB, $141.720.044— y salieron **63 alertas**. Dos fuentes de ruido, las
dos nuestras:

1. **48 alertas de tarifa sobre una factura sin EPS.** El RIPS de la
   Resolución 2275 no dice quién paga. Sin pagador no existe «tarifa
   pactada», pero la búsqueda caía al catálogo oficial del HUS y comparaba
   la factura contra el precio propio del hospital. Y encima la respuesta
   decía en `omisiones` que la tarifa NO se había cruzado: el tablero se
   contradecía a sí mismo.

2. **Un insumo BLOQUEADO por «servicio pediátrico en un paciente adulto».**
   Era `FMQ0098`, y «pediátrico» ahí es un CALIBRE. Una sonda pediátrica se
   le pone a un adulto todos los días.

Lo que estas pruebas cuidan es que ninguno vuelva, y —tan importante— que
arreglarlos no haya debilitado las reglas donde sí sirven.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import TarifaContratadaRecord
from app.services.preauditoria_contrato import PayloadFactura
from app.services.preauditoria_reglas_duras import (
    Contexto,
    regla_cruce_edad,
    regla_topes_tarifarios,
)

CTX = Contexto(ahora=datetime(2026, 9, 4))


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


def _factura(eps: str, items: list[dict], **kw) -> PayloadFactura:
    base = {
        "factura": "HUS559077",
        "eps": eps,
        "paciente": {"sexo": "F", "edad_anios": 46},
        "atencion": {"fecha_ingreso": "2026-09-01", "fecha_egreso": "2026-09-04"},
        "items": items,
    }
    base.update(kw)
    return PayloadFactura(**base)


def _item(**kw) -> dict:
    base = {"cups": "", "descripcion": "", "tipo": "", "cantidad": 1, "valor_unitario": 0}
    base.update(kw)
    return base


# ═══════════════════════════════════════════════════════════════════════
class TestSinEpsNoSeOpinaDeTarifas:
    """Sin pagador no hay tarifa pactada. Comparar contra el precio propio
    del hospital y llamarlo «tarifa pactada» es otra cosa."""

    def _con_catalogo(self, db):
        """Deja cargada una tarifa que SÍ existiría si hubiera EPS."""
        db.add(
            TarifaContratadaRecord(
                eps="COOSALUD",
                codigo_cups="890201",
                descripcion="CONSULTA",
                valor_pactado=60_000,
                tipo_tarifa="VALOR_FIJO",
            )
        )
        db.commit()

    def test_una_factura_sin_eps_no_dispara_ni_una_alerta_de_tarifa(self, db):
        """El caso de HUS559077: 48 bloqueos que nadie podía resolver."""
        self._con_catalogo(db)
        p = _factura("", [_item(cups="890201", tipo="CONSULTA", valor_unitario=999_000)])
        assert regla_topes_tarifarios(p, Contexto(db=db)) == []

    def test_una_eps_en_blancos_cuenta_como_sin_eps(self, db):
        self._con_catalogo(db)
        p = _factura("   ", [_item(cups="890201", tipo="CONSULTA", valor_unitario=999_000)])
        assert regla_topes_tarifarios(p, Contexto(db=db)) == []

    def test_con_eps_la_regla_sigue_trabajando_igual(self, db):
        """Lo importante del arreglo: no se apagó la regla, se acotó."""
        self._con_catalogo(db)
        p = _factura("COOSALUD", [_item(cups="890201", tipo="CONSULTA", valor_unitario=90_000)])
        alertas = regla_topes_tarifarios(p, Contexto(db=db))
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].valor_en_riesgo == 30_000

    def test_el_dia_que_el_his_mande_la_eps_vuelve_a_operar(self, db):
        """Misma factura, mismo ítem: lo único que cambia es el pagador."""
        self._con_catalogo(db)
        item = _item(cups="890201", tipo="CONSULTA", valor_unitario=999_000)
        assert regla_topes_tarifarios(_factura("", [item]), Contexto(db=db)) == []
        assert regla_topes_tarifarios(_factura("COOSALUD", [item]), Contexto(db=db)) != []


# ═══════════════════════════════════════════════════════════════════════
class TestEnUnInsumoLaEdadEsUnaTalla:
    """«Pediátrico» en un dispositivo es un calibre; en una estancia es un
    paciente. La regla tiene que distinguirlo."""

    PACIENTE_ADULTO = {"sexo": "F", "edad_anios": 46}

    def test_el_insumo_pediatrico_en_un_adulto_ya_no_bloquea(self):
        """FMQ0098, el caso real. Una sonda pediátrica es un calibre."""
        p = _factura(
            "COOSALUD",
            [
                _item(
                    cups="FMQ0098",
                    descripcion="SONDA PEDIATRICA",
                    tipo="DISPOSITIVO",
                    valor_unitario=94_600,
                )
            ],
            paciente=self.PACIENTE_ADULTO,
        )
        assert regla_cruce_edad(p, CTX) == []

    def test_un_medicamento_neonatal_en_un_adulto_tampoco(self):
        """Es una dosis, no un paciente."""
        p = _factura(
            "COOSALUD",
            [
                _item(
                    cups="M0001",
                    descripcion="AMPICILINA SUSPENSION NEONATAL",
                    tipo="MEDICAMENTO",
                    valor_unitario=15_000,
                )
            ],
            paciente=self.PACIENTE_ADULTO,
        )
        assert regla_cruce_edad(p, CTX) == []

    def test_pero_la_uci_pediatrica_en_un_adulto_SIGUE_bloqueando(self):
        """La prueba que impide que el arreglo se lleve la regla puesta:
        una estancia sí habla del paciente."""
        p = _factura(
            "COOSALUD",
            [
                _item(
                    cups="S11202",
                    descripcion="ESTANCIA EN UCI PEDIATRICA",
                    tipo="ESTANCIA",
                    valor_unitario=1_500_000,
                )
            ],
            paciente=self.PACIENTE_ADULTO,
        )
        alertas = regla_cruce_edad(p, CTX)
        assert len(alertas) == 1 and alertas[0].severidad == "BLOQUEO"

    def test_y_un_procedimiento_neonatal_en_un_adulto_tambien(self):
        p = _factura(
            "COOSALUD",
            [
                _item(
                    cups="731001",
                    descripcion="REANIMACION DEL RECIEN NACIDO",
                    tipo="QUIRURGICO",
                    valor_unitario=800_000,
                )
            ],
            paciente=self.PACIENTE_ADULTO,
        )
        assert regla_cruce_edad(p, CTX)[0].severidad == "BLOQUEO"

    def test_un_insumo_de_adultos_en_un_nino_tampoco_bloquea(self):
        """El espejo del caso real: también es una talla."""
        p = _factura(
            "COOSALUD",
            [
                _item(
                    cups="FMQ0100",
                    descripcion="PAÑAL ADULTO",
                    tipo="DISPOSITIVO",
                    valor_unitario=3_000,
                )
            ],
            paciente={"sexo": "M", "edad_anios": 6},
        )
        assert regla_cruce_edad(p, CTX) == []
