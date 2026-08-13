"""El texto fijo del Dispensario, solo cuando el tema calce.

Prueba real del 05-08-2026, glosa de trampa Nº 1 (EPS = DISPENSARIO MEDICO):

    "TA0801 GLOSA POR TARIFA. SE OBJETA VALOR DE HABITACIÓN UNIPERSONAL
     COBRADA COMO SUITE, ADICIONALMENTE SE COBRAN INSUMOS NO PACTADOS, EL
     OXÍGENO SE LIQUIDA POR HORA Y EL CONTRATO DICE POR DÍA, Y NO SE
     EVIDENCIA AUTORIZACIÓN PARA LOS DÍAS 4 AL 7."

El motor respondió con el texto canónico sobre AGOTAMIENTO PRESUPUESTAL e
INEXISTENCIA DE CONTRATO. No le erró: ni la leyó. La condición miraba solo
que el código empezara por TA y que el pagador fuera el Dispensario.

Y ese camino no pasa por el control de calidad —el Quality Gate vive en la
rama de IA—, así que nadie detectó la incoherencia ni que el texto citaba
una norma derogada.

Decisión de Yesid ese día: el texto canónico sigue, pero solo cuando el
tema calce. Las demás glosas TA del Dispensario van al motor con su
control de calidad.
"""

from __future__ import annotations

from app.services.glosa_service import (
    TEXTO_DMBUG_TARIFAS,
    _es_dispensario_medico,
    _glosa_es_del_tema_dmbug,
)

GLOSA_QUE_NO_CALZA = (
    "TA0801 GLOSA POR TARIFA. SE OBJETA VALOR DE HABITACIÓN UNIPERSONAL "
    "COBRADA COMO SUITE, ADICIONALMENTE SE COBRAN INSUMOS NO PACTADOS, EL "
    "OXÍGENO SE LIQUIDA POR HORA Y EL CONTRATO DICE POR DÍA, Y NO SE "
    "EVIDENCIA AUTORIZACIÓN PARA LOS DÍAS 4 AL 7. VALOR OBJETADO $4.860.000."
)


class TestElTemaDecide:
    def test_la_glosa_que_engano_al_motor_ya_no_calza(self):
        assert _glosa_es_del_tema_dmbug(GLOSA_QUE_NO_CALZA) is False

    def test_lo_que_el_texto_canonico_si_refuta(self):
        for texto in (
            "TA0301 SE OBJETA POR AGOTAMIENTO PRESUPUESTAL DE LA VIGENCIA",
            "TA0301 NO EXISTE CONTRATO VIGENTE CON LA ESE",
            "TA0301 SE LIQUIDA POR SOAT AL NO HABER TARIFA PACTADA",
            "TA0301 SE APLICA EL DECRETO 2423 DE 1996",
            "TA0301 SIN DISPONIBILIDAD PRESUPUESTAL PARA LA VIGENCIA",
        ):
            assert _glosa_es_del_tema_dmbug(texto) is True, texto

    def test_texto_vacio_no_calza(self):
        assert _glosa_es_del_tema_dmbug("") is False
        assert _glosa_es_del_tema_dmbug(None) is False

    def test_el_pagador_se_sigue_reconociendo_igual(self):
        for eps in (
            "DISPENSARIO MEDICO",
            "DMBUG",
            "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG",
        ):
            assert _es_dispensario_medico(eps) is True
        assert _es_dispensario_medico("NUEVA EPS") is False


class TestLaNormaDerogada:
    """El texto canónico citaba la Resolución 3047 de 2008, derogada por la
    2284 de 2023. Corregido por decisión de Yesid el 05-08-2026."""

    def test_ya_no_cita_la_3047(self):
        assert "3047" not in TEXTO_DMBUG_TARIFAS

    def test_cita_la_vigente(self):
        assert "2284 DE 2023" in TEXTO_DMBUG_TARIFAS
        assert "MANUAL ÚNICO DE DEVOLUCIONES, GLOSAS Y RESPUESTAS" in TEXTO_DMBUG_TARIFAS

    def test_lo_demas_del_texto_queda_intacto(self):
        """El resto lo aprobó el auditor: contrato, anexo y fundamento."""
        for pedazo in (
            "440-DIGSA/DMBUG-2025",
            "7.141 ÍTEMS TARIFADOS",
            "AGOTAMIENTO PRESUPUESTAL",
            "ARTÍCULOS 1602 Y 1603 DEL CÓDIGO CIVIL",
            "DECRETO-LEY 1795 DE 2000",
        ):
            assert pedazo in TEXTO_DMBUG_TARIFAS, pedazo

    def test_la_plantilla_gold_vieja_se_corrige_sola(self):
        """La plantilla ya sembrada en la base alimenta los ejemplos que ve
        la IA: si quedó con la norma derogada, el arranque la corrige."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent.parent
        main = (raiz / "app" / "main.py").read_text(encoding="utf-8")
        assert 'if "3047" in (existe.argumento or "")' in main
        assert "gold_actualizadas" in main
