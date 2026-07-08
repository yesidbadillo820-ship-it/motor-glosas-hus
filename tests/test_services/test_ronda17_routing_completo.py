"""Tests de regresión ronda 17 (26-jun-2026) — brechas de routing detectadas
en auditoría exhaustiva tras merge de ronda 16.

Auditoría con 3 verificadores independientes confirmó por unanimidad que
el fix de ronda 16 (R-CEREBRO #5 + override en _llamar_ia) funcionaba
SOLO en 3 de 6 caminos del motor. Casos complejos (Cart-T, Norwood,
hemofilia, valor ≥ $50M) seguían cayendo en Llama 4 Scout cuando:

  1. QUALITY_GATE_ENABLED=1 (típico en producción) — el QG decidía su
     propio modelo via su router interno ignorando R-CEREBRO #5.
  2. Multi-código — cada sección adicional pasaba por el QG sin re-evaluar
     complejidad. El principal escalaba a Claude, los adicionales no.
  3. Auto-crítica refinamiento (R-CEREBRO #1 retry) — no propagaba override.
  4. refinar_dictamen (chat con el auditor) — no detectaba complejidad.

Fix de ronda 17:
  • Helper compartido detectar_complejidad_critica + lista única de
    palabras-clave (routing_complejidad.py).
  • Quality Gate adapter acepta modelo_override_forzado.
  • Multi-código re-evalúa complejidad por sección.
  • Auto-crítica reusa _modelo_override.
  • refinar_dictamen detecta complejidad sobre el dictamen actual.
  • ia_router incluye palabras-clave críticas en clasificar_complejidad.
"""

import inspect

from app.services.ia_router import clasificar_complejidad, enrutar
from app.services.routing_complejidad import (
    PALABRAS_CLAVE_COMPLEJIDAD_CRITICA,
    detectar_complejidad_critica,
)


class TestDetectorComplejidadCritica:
    def test_valor_50m_es_complejo(self):
        r = detectar_complejidad_critica(valor=50_000_000)
        assert r.es_complejo is True
        assert any("valor" in m for m in r.motivos)

    def test_valor_5m_y_2_pdfs_es_complejo(self):
        r = detectar_complejidad_critica(valor=5_000_000, num_pdfs=2)
        assert r.es_complejo is True

    def test_valor_4m_y_2_pdfs_no_es_complejo(self):
        # Solo dispara si valor >= 5M Y pdfs >= 2
        r = detectar_complejidad_critica(valor=4_000_000, num_pdfs=2)
        assert r.es_complejo is False

    def test_3_codigos_es_complejo(self):
        r = detectar_complejidad_critica(num_codigos=3)
        assert r.es_complejo is True

    def test_texto_largo_es_complejo(self):
        r = detectar_complejidad_critica(texto_glosa="x" * 4001)
        assert r.es_complejo is True

    def test_palabra_clave_cart_t_es_complejo(self):
        r = detectar_complejidad_critica(
            texto_glosa="se objeta TISAGENLECLEUCEL en linfoma refractario"
        )
        assert r.es_complejo is True
        assert any("palabra-clave-critica" in m for m in r.motivos)

    def test_palabra_clave_norwood_es_complejo(self):
        r = detectar_complejidad_critica(texto_glosa="cirugía de NORWOOD neonatal")
        assert r.es_complejo is True

    def test_palabra_clave_epicel_es_complejo(self):
        r = detectar_complejidad_critica(texto_glosa="aplicación de epicel en quemados")
        assert r.es_complejo is True

    def test_palabra_clave_tutela_es_complejo(self):
        r = detectar_complejidad_critica(texto_glosa="sentencia de tutela T-553/2024")
        assert r.es_complejo is True

    def test_palabra_clave_en_contexto_pdf_tambien_dispara(self):
        # Si la palabra-clave SOLO está en PDFs, también dispara
        r = detectar_complejidad_critica(
            texto_glosa="glosa común",
            contexto_pdf="HISTORIA CLÍNICA del paciente con HEMOFILIA tipo A grave",
        )
        assert r.es_complejo is True

    def test_caso_simple_no_es_complejo(self):
        r = detectar_complejidad_critica(
            valor=200_000,
            num_pdfs=0,
            num_codigos=1,
            texto_glosa="tarifa pactada SOAT no aplica",
            contexto_pdf="",
        )
        assert r.es_complejo is False
        assert r.motivos == []


class TestPalabrasClaveCriticas:
    """La lista debe cubrir todos los grupos clínicos identificados en rondas 14-16."""

    def test_oncologia_alto_costo(self):
        assert "CART-T" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA
        assert "TISAGENLECLEUCEL" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_cardiopatias_congenitas(self):
        assert "NORWOOD" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_trasplantes(self):
        assert "TRASPLANT" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_hematologicas_huerfanas(self):
        assert "HEMOFILIA" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA
        assert "GAUCHER" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_quemados(self):
        assert "EPICEL" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_terapias_genicas(self):
        assert "ZOLGENSMA" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA
        assert "NUSINERSEN" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_tutelas_recobros(self):
        assert "TUTELA" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA
        assert "RECOBRO" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA

    def test_eventos_adversos(self):
        assert "EVENTO ADVERSO" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA
        assert "PREVENIBLE" in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA


class TestRouterQGDetectaPalabrasClave:
    """Bug confirmado por verificadores: el router del QG (ia_router.py)
    no detectaba palabras-clave críticas. Un Cart-T con valor<1M y un
    solo código caía en SIMPLE/MEDIA y se generaba con Llama."""

    def test_cart_t_valor_bajo_un_codigo_se_clasifica_compleja(self):
        # Caso antes del fix: valor 500K (<1M threshold) + 1 código + CART-T
        # caía en MEDIA → groq. Ahora debe ser COMPLEJA → anthropic.
        comp = clasificar_complejidad(
            valor=500_000,
            texto_glosa="aplicación de CART-T en linfoma refractario",
            codigo_glosa="CO0701",
        )
        assert comp == "COMPLEJA"

    def test_norwood_neonatal_se_clasifica_compleja(self):
        comp = clasificar_complejidad(
            valor=300_000,
            texto_glosa="cirugía estadiada de NORWOOD para HLHS",
            codigo_glosa="CL0801",
        )
        assert comp == "COMPLEJA"

    def test_tutela_se_clasifica_compleja(self):
        comp = clasificar_complejidad(
            valor=200_000,
            texto_glosa="cumplimiento de SENTENCIA DE TUTELA",
            codigo_glosa="AU0301",
        )
        assert comp == "COMPLEJA"

    def test_caso_simple_sigue_simple(self):
        # Valor bajo, 1 código simple, sin palabras-clave: SIMPLE/MEDIA
        comp = clasificar_complejidad(
            valor=100_000,
            texto_glosa="tarifa SOAT no pactada",
            codigo_glosa="TA0201",
            tiene_soportes_pdf=True,
        )
        # debe ser SIMPLE (tiene soportes + valor bajo)
        assert comp == "SIMPLE"

    def test_enrutar_cart_t_va_a_anthropic(self):
        decision = enrutar(
            eps="SURA",
            valor=500_000,
            texto_glosa="aplicación de CART-T (Tisagenlecleucel) en LNH",
            codigo_glosa="CO0701",
            proveedores_disponibles={"groq", "anthropic"},
        )
        assert decision.complejidad == "COMPLEJA"
        assert decision.modelo_recomendado == "anthropic"


class TestQGAdapterAceptaOverrideForzado:
    """El adapter del QG debe exponer modelo_override_forzado para que
    R-CEREBRO #5 propague su señal de complejidad."""

    def test_signature_acepta_modelo_override_forzado(self):
        from app.services.quality_gate_adapter import ejecutar_con_quality_gate

        sig = inspect.signature(ejecutar_con_quality_gate)
        assert "modelo_override_forzado" in sig.parameters
        assert sig.parameters["modelo_override_forzado"].default is None

    def test_signature_acepta_contexto_pdf(self):
        from app.services.quality_gate_adapter import ejecutar_con_quality_gate

        sig = inspect.signature(ejecutar_con_quality_gate)
        assert "contexto_pdf" in sig.parameters


class TestMultiCodigoReEvaluaComplejidad:
    """Cada código adicional debe re-evaluar complejidad y propagar override."""

    def test_multi_codigo_importa_detector_compartido(self):
        # Verifica que multi_codigo importa y usa el helper compartido.
        import app.services.multi_codigo as mc

        src = inspect.getsource(mc)
        assert "detectar_complejidad_critica" in src
        assert "modelo_override_forzado" in src

    def test_glosa_service_importa_detector_compartido(self):
        # El R-CEREBRO #5 debe usar el helper compartido (DRY con ronda 17).
        import app.services.glosa_service as gs

        src = inspect.getsource(gs)
        assert "from app.services.routing_complejidad import" in src
        assert "detectar_complejidad_critica" in src


class TestAutoCriticaReusaOverride:
    """La auto-crítica de R-CEREBRO #1 (línea ~5187 después del fix) debe
    pasar modelo_override=_modelo_override en la llamada de refinamiento."""

    def test_auto_critica_pasa_modelo_override(self):
        import app.services.glosa_service as gs

        src = inspect.getsource(gs)
        # El refinamiento de auto-crítica vive dentro de un bloque que
        # contiene "score=…→refinado". Buscamos esa firma y la ventana
        # incluye el call _llamar_ia que la precede.
        idx_refinado_log = src.find("→refinado")
        assert idx_refinado_log > 0, "marker '→refinado' not found"
        # Ventana amplia: 2500 chars hacia atrás (donde está _res_refinado
        # = await self._llamar_ia(...)) y 500 hacia adelante.
        ventana = src[max(0, idx_refinado_log - 2500) : idx_refinado_log + 500]
        assert "modelo_override=_modelo_override" in ventana


class TestRefinarDictamenDetectaComplejidad:
    """refinar_dictamen (chat_glosa) debe detectar complejidad sobre el
    dictamen actual + instrucción del auditor, y forzar Anthropic si aplica."""

    def test_refinar_dictamen_usa_detector_compartido(self):
        import app.services.glosa_service as gs

        src = inspect.getsource(gs)
        # Buscamos en la función refinar_dictamen el detector compartido
        idx_refinar = src.find("async def refinar_dictamen")
        assert idx_refinar > 0
        # Tomamos el cuerpo de la función (hasta la siguiente def)
        siguiente = src.find("\n    def ", idx_refinar + 10)
        siguiente_async = src.find("\n    async def ", idx_refinar + 10)
        siguiente_real = (
            min(s for s in (siguiente, siguiente_async) if s > 0)
            if any(s > 0 for s in (siguiente, siguiente_async))
            else len(src)
        )
        cuerpo = src[idx_refinar:siguiente_real]
        assert "detectar_complejidad_critica" in cuerpo
        assert "modelo_override=_modelo_override_refinar" in cuerpo


class TestNormalizarMayusculasProtegeHTMLyCodigosHifenados:
    """Bug regresión detectado en CI tras ronda 16 (umbral 0.45): el
    sanitizer lowercase HTML estructural y códigos de contrato hifenados
    como S-13-1-03-1-04958. Rompía test_optimizaciones_tokens y
    test_multi_codigo. Fix de ronda 17: skip si hay HTML estructural,
    preserva códigos hifenados con placeholder."""

    def test_codigo_contrato_hifenado_se_preserva(self):
        from app.services.glosa_service import _normalizar_mayusculas_sostenidas

        texto = (
            "ESE HUS NO ACEPTA LA GLOSA TA0301 INTERPUESTA POR FAMISANAR EPS, "
            "POR CUANTO EL VALOR FACTURADO COINCIDE EXACTAMENTE CON LA TARIFA "
            "PACTADA EN EL S-13-1-03-1-04958 PARA EL CUPS 890202."
        )
        res = _normalizar_mayusculas_sostenidas(texto)
        # El código de contrato debe quedar en mayúsculas exactas
        assert "S-13-1-03-1-04958" in res

    def test_sentencia_t553_2024_se_preserva(self):
        from app.services.glosa_service import _normalizar_mayusculas_sostenidas

        texto = (
            "ESTE HUS INVOCA LA SENTENCIA T-553/2024 DE LA CORTE CONSTITUCIONAL "
            "QUE GARANTIZA EL ACCESO BAJO ORDEN JUDICIAL."
        )
        res = _normalizar_mayusculas_sostenidas(texto)
        assert "T-553/2024" in res

    def test_html_estructural_no_se_toca(self):
        from app.services.glosa_service import _normalizar_mayusculas_sostenidas

        html = (
            '<table border="1" style="width:100%"><tr>'
            "<th>CÓDIGO GLOSA</th></tr></table>"
            '<div style="background:#f8fafc;">ESE HUS NO ACEPTA LA GLOSA</div>'
        )
        res = _normalizar_mayusculas_sostenidas(html)
        # No debe haber tocado nada
        assert res == html
        # Específicamente: el header CÓDIGO GLOSA debe seguir uppercase
        assert "<th>CÓDIGO GLOSA</th>" in res

    def test_texto_plano_se_normaliza(self):
        # Garantiza que el sanitizer aún normaliza texto plano (no es no-op)
        from app.services.glosa_service import _normalizar_mayusculas_sostenidas

        texto = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR FAMISANAR EPS. SE SOLICITA EL LEVANTAMIENTO."
        )
        res = _normalizar_mayusculas_sostenidas(texto)
        # Debe normalizar a sentence case
        assert res != texto
        # Pero conserva siglas conocidas
        assert "HUS" in res
        assert "EPS" in res
        assert "FAMISANAR" in res


class TestRegresionRonda16:
    """Los fixes de ronda 16 siguen funcionando — sanitizers, corpus, prompt."""

    def test_ronda16_corpus_normas_intactas(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        assert "SENTENCIA T-553 DE 2024" in _TODAS_LAS_NORMAS
        assert "AUTO 037 DE 2024" in _TODAS_LAS_NORMAS

    def test_ronda16_sanitizer_sancion_intacto(self):
        from app.services.glosa_service import _rechazar_sancion_eps_ilegal

        dictamen = "EL HUS SE AJUSTA A LA SANCIÓN APLICADA POR LA EPS."
        res = _rechazar_sancion_eps_ilegal(dictamen, texto_glosa="SANCIÓN DEL 8%")
        assert "rechaza" in res.lower() or "RECHAZA" in res

    def test_ronda16_post_validador_instrucciones_intacto(self):
        from app.services.glosa_service import _auditar_instrucciones_gestor

        cumplido, omisiones = _auditar_instrucciones_gestor(
            "ESE HUS cita la Sentencia T-553/2024",
            instrucciones_gestor="Incluir la Sentencia T-553/2024",
        )
        assert cumplido is True
