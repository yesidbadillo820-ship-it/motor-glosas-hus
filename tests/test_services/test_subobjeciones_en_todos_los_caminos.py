"""Cuando la glosa trae varias objeciones, se responden todas.

Prueba real del 05-08-2026, glosa de trampa Nº 1 — CUATRO objeciones bajo
un solo código TA0801:

    habitación unipersonal cobrada como suite · insumos no pactados ·
    oxígeno liquidado por hora cuando el contrato dice por día ·
    días 4 al 7 sin autorización

El dictamen contestó un párrafo genérico sobre tarifas y dejó tres mudas.
En auditoría, callar sobre un concepto equivale a aceptarlo: la EPS
descuenta lo que no se refutó.

El detector de sub-conceptos existía y estaba enganchado… pero vivía
DENTRO de la rama de IA. En los caminos de texto fijo no llegaba a
ejecutarse, así que el aviso de «conceptos sin responder» no aparecía justo
donde más falta hacía — que fue exactamente lo que pasó con esta glosa,
respondida con la plantilla fija del Dispensario.
"""

from __future__ import annotations

import inspect

from app.services.glosa_service import GlosaService, _glosa_es_del_tema_dmbug
from app.services.subconceptos_glosa import detectar_subconceptos

GLOSA_4_OBJECIONES = (
    "TA0801 GLOSA POR TARIFA. SE OBJETA VALOR DE HABITACIÓN UNIPERSONAL "
    "COBRADA COMO SUITE, ADICIONALMENTE SE COBRAN INSUMOS NO PACTADOS, EL "
    "OXÍGENO SE LIQUIDA POR HORA Y EL CONTRATO DICE POR DÍA, Y NO SE "
    "EVIDENCIA AUTORIZACIÓN PARA LOS DÍAS 4 AL 7. VALOR OBJETADO $4.860.000."
)


class TestSeDetectanLasVariasObjeciones:
    def test_la_glosa_del_caso_trae_mas_de_una(self):
        assert len(detectar_subconceptos(GLOSA_4_OBJECIONES)) >= 2

    def test_una_glosa_de_un_solo_motivo_no_se_parte(self):
        simple = "SO0201 FALTA EPICRISIS. VALOR $890.000."
        assert len(detectar_subconceptos(simple)) < 2


class TestLaDeteccionAlcanzaTodosLosCaminos:
    """Estaba dentro de la rama de IA: los caminos de texto fijo no la veían."""

    def test_se_detecta_antes_de_elegir_el_camino(self):
        src = inspect.getsource(GlosaService.analizar)
        i_det = src.index("[SUBCONCEPTOS]")
        i_texto_fijo = src.index("argumento_fijo = TEXTO_RATIFICADA")
        assert i_det < i_texto_fijo, (
            "la detección de sub-conceptos volvió a quedar después de elegir "
            "el camino: los de texto fijo no la verán"
        )

    def test_el_aviso_de_conceptos_sin_responder_sigue_enganchado(self):
        src = inspect.getsource(GlosaService.analizar)
        assert "_subconceptos_actuales" in src


class TestElTextoFijoNoTapaLasDemasObjeciones:
    """Con varias objeciones, el texto canónico refutaría una y dejaría
    mudas las otras — aunque el tema de la primera calce."""

    def test_la_condicion_exige_una_sola_objecion(self):
        src = inspect.getsource(GlosaService.analizar)
        i = src.index("_glosa_es_del_tema_dmbug(texto_base)")
        bloque = src[i : i + 500]
        assert "len(self._subconceptos_actuales) < 2" in bloque

    def test_el_tema_se_reconoce_con_y_sin_tilde(self):
        assert _glosa_es_del_tema_dmbug("TA0301 SE AGOTÓ EL PRESUPUESTO") is True
        assert _glosa_es_del_tema_dmbug("TA0301 SE AGOTO EL PRESUPUESTO") is True
