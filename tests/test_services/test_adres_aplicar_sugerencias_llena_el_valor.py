"""«Aplicar sugerencias» no puede aceptar por $0 — 19-08-2026.

`aplicar_sugerencias` copiaba la sugerencia a la decisión y no tocaba el valor
aceptado. Cuando la sugerencia aprendida del equipo era «SE ACEPTA», la glosa
quedaba aceptada con valor CERO, y la carta que se radica salía así:

    «SE IDENTIFICAN HALLAZGOS ... POR GLOSA ACEPTADA PARCIAL POR VALOR DE $0»
      3106-SE ACEPTA-OMEPRAZOL CAPSULAS ... POR VALOR DE $100.006

Declaraba aceptar $0 mientras enumeraba ítem por ítem lo que sí aceptaba, y el
hospital perdía el registro de cuánta plata reconoció. Por el camino de a una
glosa la pantalla sí llenaba el valor; por el camino en bloque, nadie.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaAdresRecord, PaqueteAdresRecord
from app.services.preauditoria_adres import aplicar_sugerencias, consultar_factura


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _paquete(db, glosas: list[dict]) -> int:
    paq = PaqueteAdresRecord(numero_paquete="31068", archivo="r.xlsx", importado_por="p")
    db.add(paq)
    db.flush()
    for g in glosas:
        base = dict(
            paquete_id=paq.id,
            factura_clave="311371",
            factura="HUS311371",
            codigo="19942122-09",
            descripcion="OMEPRAZOL CAPSULAS",
            causal_codigo="3106",
            cant_reclamada=3.0,
            cant_aprobada=1.0,
            valor_glosado=100006.0,
            cuenta_valor=True,
        )
        base.update(g)
        db.add(GlosaAdresRecord(**base))
    db.commit()
    return paq.id


class TestAceptarEnBloque:
    def test_aceptar_llena_el_valor_aceptado(self, db):
        pid = _paquete(db, [{"sugerencia": "SE ACEPTA", "confianza": "APRENDIDA"}])
        assert aplicar_sugerencias(db, paquete_id=pid, usuario="coord") == 1
        g = db.query(GlosaAdresRecord).one()
        assert g.decision == "SE ACEPTA"
        assert g.valor_aceptado == 100006.0, "aceptó sin decir cuánta plata"

    def test_aceptar_llena_la_cantidad_glosada_no_la_reclamada(self, db):
        """Reclamó 3, le aprobaron 1: en discusión hay 2, no 3."""
        pid = _paquete(db, [{"sugerencia": "SE ACEPTA", "confianza": "APRENDIDA"}])
        aplicar_sugerencias(db, paquete_id=pid, usuario="coord")
        assert db.query(GlosaAdresRecord).one().cantidad_aceptada == "2"

    def test_el_kpi_de_la_factura_deja_de_decir_cero(self, db):
        pid = _paquete(db, [{"sugerencia": "SE ACEPTA", "confianza": "APRENDIDA"}])
        aplicar_sugerencias(db, paquete_id=pid, usuario="coord")
        d = consultar_factura(db, "HUS311371", paquete_id=pid)
        assert d["resumen"]["valor_aceptado"] == 100006.0

    def test_objetar_o_subsanar_no_reconoce_plata(self, db):
        pid = _paquete(
            db,
            [
                {"sugerencia": "SE OBJETA", "confianza": "REGLA"},
                {"sugerencia": "SE SUBSANA", "confianza": "REGLA", "causal_codigo": "3201"},
            ],
        )
        assert aplicar_sugerencias(db, paquete_id=pid, usuario="coord") == 2
        assert all(not (g.valor_aceptado or 0) for g in db.query(GlosaAdresRecord).all()), (
            "objetar o subsanar no reconoce plata"
        )

    def test_no_pisa_un_valor_que_el_gestor_ya_habia_puesto(self, db):
        """Si el gestor aceptó parcial a mano, el bloque no se lo sube."""
        pid = _paquete(
            db,
            [{"sugerencia": "SE ACEPTA", "confianza": "APRENDIDA", "valor_aceptado": 40000.0}],
        )
        aplicar_sugerencias(db, paquete_id=pid, usuario="coord")
        assert db.query(GlosaAdresRecord).one().valor_aceptado == 40000.0

    def test_glosa_de_tarifa_declara_la_cantidad_reclamada(self, db):
        """1 reclamado y 1 aprobado: no le quitaron ítems, le bajaron el precio."""
        pid = _paquete(
            db,
            [
                {
                    "sugerencia": "SE ACEPTA",
                    "confianza": "APRENDIDA",
                    "cant_reclamada": 1.0,
                    "cant_aprobada": 1.0,
                    "valor_glosado": 100.0,
                }
            ],
        )
        aplicar_sugerencias(db, paquete_id=pid, usuario="coord")
        assert db.query(GlosaAdresRecord).one().cantidad_aceptada == "1"


class TestNoSeDeclaraDobleNiEnBloque:
    def test_el_mismo_item_en_dos_causales_se_acepta_una_vez(self, db):
        """El caso del TAC, pero llegando por el botón de aplicar sugerencias."""
        pid = _paquete(
            db,
            [
                {"sugerencia": "SE ACEPTA", "confianza": "APRENDIDA", "causal_codigo": "3209"},
                {
                    "sugerencia": "SE ACEPTA",
                    "confianza": "APRENDIDA",
                    "causal_codigo": "3106",
                    "cuenta_valor": False,
                },
            ],
        )
        aplicar_sugerencias(db, paquete_id=pid, usuario="coord")
        d = consultar_factura(db, "HUS311371", paquete_id=pid)
        assert d["resumen"]["valor_aceptado"] == 100006.0, "se declaró el doble"
        assert d["resumen"]["valor_aceptado"] <= d["resumen"]["valor_glosado"]
