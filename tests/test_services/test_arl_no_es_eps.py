"""A una ARL no se le responde con el régimen de salud común.

Prueba real del 05-08-2026, glosa de trampa Nº 4:

    "POSITIVA COMPAÑÍA DE SEGUROS — GLOSA CO0102: SERVICIO NO CUBIERTO POR
     EL SISTEMA GENERAL DE SEGURIDAD SOCIAL EN SALUD. ACCIDENTE DE TRABAJO.
     VALOR $12.300.000."

El dictamen citó Ley 1438/2011, Resolución 2284/2023 y «plan de
beneficios» — el marco del SGSSS. Siendo accidente de trabajo, el marco es
riesgos laborales: Decreto-Ley 1295/1994, Ley 1562/2012, Ley 776/2002.

Y el motor YA TENÍA el bloque ARL correcto. Lo que pasaba es que otras dos
partes del prompt lo contradecían, y ganaba la orden más concreta:

  1. Cuando no hay plantilla de esa aseguradora, el banco de ejemplos cae
     a las genéricas — escritas para EPS, con PBS y UPC. El modelo copia
     el ejemplo que tiene delante.
  2. El aviso de «aseguradora SOAT» mete a las ARL en la misma bolsa y le
     ordenaba citar el Art. 177 de la Ley 100: justo la norma que el
     bloque ARL prohíbe.
"""

from __future__ import annotations

from app.services.glosa_ia_prompts import _REGLA_ARL_ESTRATEGICA, _es_pagador_arl

GLOSA_ARL = (
    "POSITIVA COMPAÑÍA DE SEGUROS — GLOSA CO0102: SERVICIO NO CUBIERTO POR EL "
    "SISTEMA GENERAL DE SEGURIDAD SOCIAL EN SALUD. ACCIDENTE DE TRABAJO. "
    "VALOR $12.300.000."
)


class TestSeReconoceElRegimen:
    def test_positiva_con_accidente_de_trabajo(self):
        assert _es_pagador_arl("POSITIVA", GLOSA_ARL) is True

    def test_una_eps_del_regimen_comun_no(self):
        assert _es_pagador_arl("NUEVA EPS", "SO0201 FALTA EPICRISIS") is False


class TestNoSeLeSirvenEjemplosDelRegimenEquivocado:
    """Mejor sin ejemplo que con ejemplo del régimen errado."""

    def test_a_una_arl_no_se_le_pasan_plantillas_genericas(self):
        import inspect

        from app.api.routers import analizar

        src = inspect.getsource(analizar._obtener_few_shots)
        assert "_es_pagador_arl" in src
        assert "return [], [], cod_pref" in src


class TestElPromptYaNoSeContradice:
    def test_la_regla_arl_desactiva_los_argumentos_de_pbs(self):
        r = _REGLA_ARL_ESTRATEGICA.upper()
        assert "PLAN DE BENEFICIOS" in r
        assert "NO LO COPIES NI LO ADAPTES" in r
        assert "COBERTURA ES INTEGRAL" in r

    def test_la_regla_sigue_prohibiendo_la_ley_100_como_regimen(self):
        r = _REGLA_ARL_ESTRATEGICA
        assert "NO citar Ley 100" in r
        assert "Decreto-Ley 1295/1994" in r
        assert "Ley 1562/2012" in r

    def test_el_aviso_de_aseguradora_no_ordena_citar_ley_100_a_una_arl(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("ALERTA CRÍTICA: ASEGURADORA SOAT")
        bloque = src[max(0, i - 1200) : i + 1200]
        assert "_es_arl_caso" in bloque
        assert "NO cites Ley 100 ni PBS" in bloque
