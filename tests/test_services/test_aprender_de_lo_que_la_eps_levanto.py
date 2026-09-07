"""Cerrar el ciclo: aprender de lo que la EPS sí levantó.

Idea del 26-08-2026. El motor guardaba plantillas «gold», pero nadie cerraba
el ciclo: cuando una EPS levanta una glosa, el gestor sabe POR QUÉ, y esa
frase —la mejor prueba que existe de qué argumento funciona— se quedaba en
el aire. Ahora se le pregunta al registrar la decisión y queda pegada a la
plantilla.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord, PlantillaGoldRecord
from app.services.aprendizaje_feedback import (
    _notas_de_la_promocion,
    aprender_de_decision_eps,
)

ARGUMENTO = (
    "ESE HUS NO ACEPTA LA GLOSA. EL SERVICIO FACTURADO CORRESPONDE AL PACTADO "
    "EN EL CONTRATO VIGENTE ENTRE LAS PARTES Y SE ENCUENTRA DEBIDAMENTE "
    "SOPORTADO EN LA HISTORIA CLÍNICA APORTADA. SE SOLICITA EL LEVANTAMIENTO "
    "TOTAL DE LA GLOSA Y EL PAGO DEL VALOR OBJETADO."
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _glosa(**kw) -> GlosaRecord:
    base = dict(
        id=1,
        eps="NUEVA EPS",
        codigo_glosa="FA0301",
        valor_objetado=1_000_000.0,
        valor_recuperado=800_000.0,
        dictamen="<p>ARGUMENTACIÓN JURÍDICA</p><p>" + ARGUMENTO + "</p>",
        modelo_ia="claude",
    )
    base.update(kw)
    return GlosaRecord(**base)


class TestLoQueDijoElGestorQuedaEscrito:
    def test_la_frase_del_gestor_entra_en_las_notas(self):
        g = _glosa(observacion_eps="Aceptaron el anexo del contrato con la tarifa pactada.")
        notas = _notas_de_la_promocion(g)
        assert "Según el gestor" in notas
        assert "anexo del contrato" in notas

    def test_sin_frase_no_se_inventa_una(self):
        notas = _notas_de_la_promocion(_glosa(observacion_eps=None))
        assert "Según el gestor" not in notas, (
            "si el gestor no anotó nada, el sistema no puede ponerle palabras"
        )
        assert "Valor recuperado" in notas, "lo que sí se sabe debe quedar"

    def test_una_frase_kilometrica_no_desborda_la_nota(self):
        notas = _notas_de_la_promocion(_glosa(observacion_eps="X" * 5000))
        assert len(notas) < 1200

    def test_espacios_en_blanco_no_cuentan_como_respuesta(self):
        notas = _notas_de_la_promocion(_glosa(observacion_eps="    \n  "))
        assert "Según el gestor" not in notas


class TestLaPlantillaPromovidaLoConserva:
    def test_al_levantar_la_glosa_la_gold_guarda_el_porque(self, db):
        glosa = _glosa(observacion_eps="Bastó adjuntar la autorización que faltaba.")
        db.add(glosa)
        db.commit()
        r = aprender_de_decision_eps(db, glosa, "LEVANTADA", "gestor@hus.com")
        assert r["accion"] == "promovida", r
        gold = db.query(PlantillaGoldRecord).filter_by(id=r["gold_id"]).first()
        assert "autorización que faltaba" in (gold.notas or ""), (
            "esa frase es la prueba de qué argumento funciona: no se puede perder"
        )

    def test_sin_valor_recuperado_no_se_promueve_nada(self, db):
        glosa = _glosa(valor_recuperado=0.0, observacion_eps="Algo dijeron.")
        db.add(glosa)
        db.commit()
        r = aprender_de_decision_eps(db, glosa, "LEVANTADA", "gestor@hus.com")
        assert r["accion"] == "skip"


class TestLaPantallaHaceLaPregunta:
    @pytest.fixture(scope="class")
    def js(self) -> str:
        html = pathlib.Path("static/index.html").read_text(encoding="utf-8")
        ini = html.find("async function registrarDecisionEPS(id)")
        assert ini > 0
        fin = html.find("\n}", html.find("catch(e)", ini))
        return html[ini:fin]

    def test_pregunta_cual_argumento_la_levanto(self, js: str):
        assert "¿Cuál argumento la levantó?" in js

    def test_solo_pregunta_cuando_la_levantaron(self, js: str):
        assert "==='LEVANTADA'" in js, (
            "no tiene sentido preguntar qué argumento ganó cuando se perdió"
        )

    def test_la_respuesta_viaja_al_servidor(self, js: str):
        assert "observacion_eps=porQue" in js.replace(" ", "")

    def test_se_puede_dejar_en_blanco(self, js: str):
        assert "Opcional" in js
        assert "if(porQue.trim())" in js.replace(" ", ""), (
            "una respuesta vacía no puede sobrescribir lo que ya estaba anotado"
        )
