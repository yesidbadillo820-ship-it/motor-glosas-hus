"""Responder de una vez las glosas que repiten causal (21-08-2026).

Pedido de Yesid, textual: «hay glosas que vienen por 7 ítems y a esos 7 ítems
se les da la misma respuesta, y hoy por hoy lo hacen uno a uno».

El caso real: en la factura HUS405724 la causal **3209** —«la ayuda diagnóstica
no tiene justificación»— viene sobre RX de pie y RX de pierna. Servicios
distintos, misma respuesta. Escribirla dos veces es trabajo regalado; con
siete, es media mañana.

LO QUE ESTAS PRUEBAS CUIDAN, que es lo que puede salir mal:

- Que el lote NO se salga de la factura ni de la causal que el gestor vio.
- Que NUNCA copie plata de una glosa a otra: cada ítem tiene su propio valor
  glosado, y compartirlo sería inventar cifras.
- Que una fila mala no tumbe el lote entero, y que se sepa por qué se omitió.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.db import Base, GlosaAdresRecord
from app.services.preauditoria_adres import causales_repetidas, responder_en_lote


@pytest.fixture()
def db():
    e = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(e)
    s = sessionmaker(bind=e)()
    try:
        yield s
    finally:
        s.close()
        e.dispose()


def _glosa(db, **kw):
    base = dict(
        paquete_id=31078,
        factura_clave="HUS405724",
        factura="HUS405724",
        causal_codigo="3209",
        causal_texto="La ayuda diagnóstica no tiene justificación",
        clasificacion="PERTINENCIA",
        valor_glosado=73500.0,
    )
    base.update(kw)
    g = GlosaAdresRecord(**base)
    db.add(g)
    db.flush()
    return g


class TestElCasoDeYesid:
    """Dos RX con la misma causal, una sola respuesta."""

    def test_se_aplica_a_las_dos(self, db):
        a = _glosa(db, codigo="21101", descripcion="RX de pie")
        b = _glosa(db, codigo="21102", descripcion="RX de pierna")
        db.commit()

        r = responder_en_lote(
            db,
            glosa_ids=[a.id, b.id],
            observacion_tecnico="LA AYUDA DIAGNÓSTICA ESTÁ JUSTIFICADA EN EL CUADRO CLÍNICO.",
            decision="SE OBJETA",
            causal_codigo="3209",
            clasificacion="PERTINENCIA",
            usuario="yesid@hus.gov.co",
        )
        assert r["aplicadas"] == 2
        assert r["omitidas"] == 0
        db.refresh(a)
        db.refresh(b)
        assert a.decision == "SE OBJETA"
        assert b.observacion_tecnico.startswith("LA AYUDA DIAGNÓSTICA")
        assert a.decidido_por == "yesid@hus.gov.co"

    def test_la_alerta_dice_cuantas_veces_viene_la_causal(self, db):
        for i in range(7):
            _glosa(db, codigo=f"2110{i}", descripcion=f"RX {i}")
        _glosa(db, causal_codigo="4506", causal_texto="El material hace parte de otro servicio")
        db.commit()

        grupos = causales_repetidas(db, paquete_id=31078, factura_clave="HUS405724")
        assert len(grupos) == 1, "una causal que viene UNA vez no es un grupo"
        assert grupos[0]["causal_codigo"] == "3209"
        assert grupos[0]["glosas"] == 7
        assert grupos[0]["sin_responder"] == 7
        assert len(grupos[0]["ids"]) == 7

    def test_la_alerta_distingue_lo_ya_respondido(self, db):
        a = _glosa(db, codigo="21101")
        _glosa(db, codigo="21102")
        a.decision = "SE OBJETA"
        db.commit()

        g = causales_repetidas(db, paquete_id=31078, factura_clave="HUS405724")[0]
        assert g["glosas"] == 2
        assert g["sin_responder"] == 1


class TestNoSeSaleDeLoQueElGestorVio:
    def test_no_toca_glosas_de_otra_factura(self, db):
        mia = _glosa(db, codigo="21101")
        ajena = _glosa(db, factura_clave="HUS999999", factura="HUS999999", codigo="21102")
        db.commit()

        r = responder_en_lote(
            db,
            glosa_ids=[mia.id, ajena.id],
            observacion_tecnico="X",
            causal_codigo="3209",
            clasificacion="PERTINENCIA",
        )
        assert r["aplicadas"] == 1
        assert r["avisos"][0]["glosa_id"] == ajena.id
        assert "otra factura" in r["avisos"][0]["motivo"]
        db.refresh(ajena)
        assert not ajena.observacion_tecnico

    def test_no_toca_glosas_de_otra_causal(self, db):
        mia = _glosa(db, codigo="21101")
        otra = _glosa(db, causal_codigo="4506", codigo="21102")
        db.commit()

        r = responder_en_lote(
            db,
            glosa_ids=[mia.id, otra.id],
            observacion_tecnico="X",
            causal_codigo="3209",
            clasificacion="PERTINENCIA",
        )
        assert r["aplicadas"] == 1
        assert "causal" in r["avisos"][0]["motivo"]

    def test_no_mezcla_la_4506_de_dos_areas(self, db):
        """La 4506 se reparte glosa por glosa entre FACTURACION y PERTINENCIA.
        Un gestor de facturación no puede arrastrar en su lote las que son de
        la médica auditora."""
        fact = _glosa(db, causal_codigo="4506", clasificacion="FACTURACION", codigo="1")
        pert = _glosa(db, causal_codigo="4506", clasificacion="PERTINENCIA", codigo="2")
        db.commit()

        r = responder_en_lote(
            db,
            glosa_ids=[fact.id, pert.id],
            observacion_tecnico="X",
            causal_codigo="4506",
            clasificacion="FACTURACION",
        )
        assert r["aplicadas"] == 1
        assert r["ids_aplicadas"] == [fact.id]

    def test_una_glosa_que_no_existe_no_tumba_el_lote(self, db):
        a = _glosa(db, codigo="21101")
        db.commit()

        r = responder_en_lote(
            db,
            glosa_ids=[a.id, 999999],
            observacion_tecnico="X",
            causal_codigo="3209",
            clasificacion="PERTINENCIA",
        )
        assert r["aplicadas"] == 1
        assert r["omitidas"] == 1
        assert "no existe" in r["avisos"][0]["motivo"]


class TestLaPlataNoSeComparte:
    def test_el_lote_no_admite_valor_ni_cantidad(self, db):
        """La protección estructural: cada ítem tiene su propio valor glosado.
        Si el lote pudiera escribir plata, una respuesta masiva podría aceptar
        $1.400.000 sobre un ítem glosado en $700.000."""
        import inspect

        fuente = inspect.signature(responder_en_lote).parameters
        assert "valor_aceptado" not in fuente
        assert "cantidad_aceptada" not in fuente

    def test_los_valores_glosados_quedan_intactos(self, db):
        a = _glosa(db, codigo="21101", valor_glosado=73500.0)
        b = _glosa(db, codigo="21102", valor_glosado=95400.0)
        db.commit()

        responder_en_lote(
            db,
            glosa_ids=[a.id, b.id],
            observacion_tecnico="X",
            decision="SE ACEPTA",
            causal_codigo="3209",
            clasificacion="PERTINENCIA",
        )
        db.refresh(a)
        db.refresh(b)
        assert a.valor_glosado == 73500.0
        assert b.valor_glosado == 95400.0
        assert not a.valor_aceptado
        assert not b.valor_aceptado


class TestLoQueSeRechazaDeEntrada:
    def test_sin_glosas_no_hay_lote(self, db):
        with pytest.raises(ValueError):
            responder_en_lote(db, glosa_ids=[], observacion_tecnico="X")

    def test_una_decision_inventada_se_rechaza(self, db):
        a = _glosa(db, codigo="21101")
        db.commit()
        with pytest.raises(ValueError, match="no válida|no valida"):
            responder_en_lote(
                db, glosa_ids=[a.id], observacion_tecnico="X", decision="SE ACEPTA A MEDIAS"
            )

    def test_demasiadas_glosas_de_golpe(self, db):
        with pytest.raises(ValueError, match="demasiadas"):
            responder_en_lote(db, glosa_ids=list(range(1, 250)), observacion_tecnico="X")

    def test_si_ninguna_existe_lo_dice(self, db):
        with pytest.raises(LookupError):
            responder_en_lote(db, glosa_ids=[111, 222], observacion_tecnico="X")


class TestSinDecisionSoloEscribeLaObservacion:
    def test_deja_la_decision_como_estaba(self, db):
        """Poder escribir la observación en lote sin decidir todavía: el gestor
        redacta primero y decide después."""
        a = _glosa(db, codigo="21101")
        a.decision = "SE OBJETA"
        db.commit()

        responder_en_lote(
            db,
            glosa_ids=[a.id],
            observacion_tecnico="TEXTO NUEVO",
            decision=None,
            causal_codigo="3209",
            clasificacion="PERTINENCIA",
        )
        db.refresh(a)
        assert a.observacion_tecnico == "TEXTO NUEVO"
        assert a.decision == "SE OBJETA"
