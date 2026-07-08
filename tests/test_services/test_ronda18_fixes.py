"""Tests de regresión ronda 18 (26-jun-2026) — 6 bugs detectados en
auditoría humana de 3 dictamens super difíciles tras desplegar ronda 16:

  • SALUD TOTAL TMS $98M — Llama 4 Scout (VM con código pre-ronda 17)
    omitió 80% de la glosa, no rechazó multa 10%, no defendió TMS.
  • ECOOPSOS IMPLANTE COCLEAR $389M — Claude Sonnet escaló bien por
    valor > $50M PERO invocó "atención inicial de urgencias" como
    muletilla en una cirugía electiva pediátrica. Evadió la Cláusula 24.
  • MEDIMÁS DA VINCI $273M — CACHE COLISIÓN: el dictamen del caso
    ECOOPSOS se sirvió del cache para este caso distinto. Además: negó
    el contrato CTR-2024-MEDIMAS-HUS citado por la EPS, evadió
    consentimiento informado, dictamen truncado en "Por lo expuesto y
    con base en".

Bugs cubiertos:
  • V — retry-por-truncamiento en Anthropic (stop_reason=max_tokens o
    final mid-oración). Antes solo Groq tenía esta protección.
  • W (CRÍTICO) — cache colisión: bump _PROMPT_CACHE_VERSION + len del
    user en la clave para invalidar viejos y detectar truncados.
  • X — extender _RE_NO_ES_URGENCIA con marcadores de cirugías electivas
    de alto costo (da Vinci, implante coclear, Norwood, TMS, Cart-T,
    Epicel, salud mental refractaria).
  • Y — sanitizer que reescribe "SIN CONTRATO PACTADO" cuando la glosa
    cita textualmente CTR-XXXX-XXX-HUS.
  • Z — auditor de cláusulas evadidas (warning, no modifica).
  • AA — reglas 8.quater/quinquies/sexies en system prompt: justificación
    clínica obligatoria para tecnología cara, respuesta por nombre a
    cláusulas citadas, prohibido negar contrato citado.
"""

import inspect

from app.services.glosa_service import (
    _PROMPT_CACHE_VERSION,
    _RE_NO_ES_URGENCIA,
    _auditar_clausulas_citadas_en_glosa,
    _detectar_contrato_citado_en_glosa,
    _reescribir_negacion_contrato,
    _termina_completo,
)


class TestBugWCacheColision:
    def test_prompt_cache_version_es_ronda18(self):
        # Bump invalida cachés viejos donde ocurrió la colisión MEDIMÁS→ECOOPSOS
        assert "r18" in _PROMPT_CACHE_VERSION

    def test_clave_cache_incluye_longitud_user(self):
        import app.services.glosa_service as gs

        src = (
            inspect.getsource(gs._llamar_ia_internal_for_tests)
            if hasattr(gs, "_llamar_ia_internal_for_tests")
            else inspect.getsource(gs)
        )
        assert "len(system)" in src and "len(user)" in src


class TestBugVTruncamientoAnthropic:
    def test_termina_completo_detecta_truncado_caso_medimas(self):
        # Caso real: dictamen terminó en "Por lo expuesto y con base en"
        truncado = (
            "ESE HUS no acepta la glosa. El servicio fue prestado. Por lo expuesto y con base en"
        )
        assert _termina_completo(truncado) is False

    def test_termina_completo_acepta_cierre_normal(self):
        completo = (
            "ESE HUS no acepta la glosa aplicada por la EPS, y solicita el "
            "LEVANTAMIENTO DE LA GLOSA."
        )
        assert _termina_completo(completo) is True

    def test_termina_completo_acepta_cierre_html(self):
        completo = "argumento jurídico </div>"
        assert _termina_completo(completo) is True

    def test_llamar_anthropic_implementa_retry_truncamiento(self):
        import app.services.glosa_service as gs

        src = inspect.getsource(gs.GlosaService._llamar_anthropic)
        # Debe inspeccionar stop_reason y reintentar
        assert "stop_reason" in src
        assert "retry_length_usado_anthropic" in src
        assert "ANTHROPIC-RETRY-LENGTH-TRUNC" in src


class TestBugXUrgenciasEnElectivos:
    def test_implante_coclear_es_electivo(self):
        assert _RE_NO_ES_URGENCIA.search("implante coclear bilateral")

    def test_da_vinci_es_electivo(self):
        assert _RE_NO_ES_URGENCIA.search("cirugía robótica da Vinci Xi")

    def test_prostatectomia_radical_es_electiva(self):
        assert _RE_NO_ES_URGENCIA.search("prostatectomía radical asistida por robot")

    def test_norwood_neonatal_es_programado(self):
        assert _RE_NO_ES_URGENCIA.search("cirugía estadiada Norwood Fontan")

    def test_cart_t_es_programado(self):
        assert _RE_NO_ES_URGENCIA.search("aplicación de Cart-T en linfoma")

    def test_tms_es_programado(self):
        assert _RE_NO_ES_URGENCIA.search("30 sesiones de TMS")

    def test_epicel_es_programado(self):
        assert _RE_NO_ES_URGENCIA.search("aplicación de Epicel queratinocitos cultivados")

    def test_esquizofrenia_refractaria(self):
        assert _RE_NO_ES_URGENCIA.search("esquizofrenia refractaria")


class TestBugYNegacionContrato:
    def test_detecta_ctr_2024_medimas(self):
        glosa = (
            "el contrato vigente CTR-2024-MEDIMAS-HUS define para "
            "prostatectomía CUPS 60.1.2.01 una tarifa de SOAT × 0.85"
        )
        assert _detectar_contrato_citado_en_glosa(glosa) is not None

    def test_detecta_clausula_24_ecoopsos(self):
        glosa = "Cláusula 24 del Contrato CTR-2025-ECOOPSOS-HUS exige cotización"
        assert _detectar_contrato_citado_en_glosa(glosa) is not None

    def test_reescribe_sin_contrato_cuando_glosa_lo_cita(self):
        glosa = "OBSERVACIONES MEDIMÁS: el contrato CTR-2024-MEDIMAS-HUS define tarifa SOAT × 0.85"
        dictamen = "Contrato: SIN CONTRATO PACTADO. El servicio fue prestado."
        resultado = _reescribir_negacion_contrato(dictamen, texto_glosa=glosa)
        assert "SIN CONTRATO PACTADO" not in resultado
        assert "según el contrato" in resultado.lower()

    def test_no_modifica_si_glosa_no_cita_contrato(self):
        glosa = "Tarifa no pactada, se reconoce SOAT pleno"
        dictamen = "Contrato: SIN CONTRATO PACTADO. El servicio fue prestado."
        resultado = _reescribir_negacion_contrato(dictamen, texto_glosa=glosa)
        assert resultado == dictamen


class TestBugZClausulasEvadidas:
    def test_detecta_clausula_evadida(self):
        glosa = "Cláusula 24 del contrato exige cotización comparativa"
        dictamen = "ESE HUS defiende el servicio con literatura clínica."
        cumplido, evadidas = _auditar_clausulas_citadas_en_glosa(dictamen, texto_glosa=glosa)
        assert cumplido is False
        assert 24 in evadidas

    def test_acepta_clausula_referenciada(self):
        glosa = "Cláusula 24 del contrato exige cotización"
        dictamen = "Respecto de la Cláusula 24, ESE HUS justifica exclusividad."
        cumplido, evadidas = _auditar_clausulas_citadas_en_glosa(dictamen, texto_glosa=glosa)
        assert cumplido is True
        assert evadidas == []

    def test_glosa_sin_clausulas_pasa(self):
        cumplido, evadidas = _auditar_clausulas_citadas_en_glosa(
            "dictamen", texto_glosa="glosa simple"
        )
        assert cumplido is True


class TestBugAAReglasPrompt:
    """Reglas 8.quater/quinquies/sexies del system prompt (ronda 18)."""

    def test_regla_defensa_tecnologia_cara(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "8.quater" in SYSTEM_BASE
        assert "DEFENSA DE TECNOLOGÍA CARA" in SYSTEM_BASE
        assert "Indicación clínica documentada en HC" in SYSTEM_BASE

    def test_regla_responder_clausulas_por_nombre(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "8.quinquies" in SYSTEM_BASE
        assert "RESPONDER POR NOMBRE A CADA CLÁUSULA" in SYSTEM_BASE
        assert "Decreto 1082/2015" in SYSTEM_BASE

    def test_regla_no_negar_contrato_citado(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "8.sexies" in SYSTEM_BASE
        assert "NUNCA NEGAR EL CONTRATO CITADO" in SYSTEM_BASE
        assert "CTR-" in SYSTEM_BASE


class TestRegresionRondaAnteriores:
    def test_ronda17_helper_routing_compartido(self):
        from app.services.routing_complejidad import detectar_complejidad_critica

        r = detectar_complejidad_critica(valor=50_000_000)
        assert r.es_complejo is True

    def test_ronda16_sanitizer_sancion_intacto(self):
        from app.services.glosa_service import _rechazar_sancion_eps_ilegal

        dictamen = "EL HUS SE AJUSTA A LA SANCIÓN APLICADA POR LA EPS."
        res = _rechazar_sancion_eps_ilegal(dictamen, texto_glosa="SANCIÓN DEL 8%")
        assert "rechaza" in res.lower() or "RECHAZA" in res

    def test_ronda14_codigo_uvb_intacto(self):
        from app.services.glosa_service import _DIGITOS_CONSTANTES_LEGITIMOS

        assert "12110" in _DIGITOS_CONSTANTES_LEGITIMOS
