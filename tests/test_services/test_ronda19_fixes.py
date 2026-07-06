"""Tests de regresión ronda 19 (30-jun-2026) — 3 bugs detectados al
probar el caso SALUD TOTAL TMS $98M tras desplegar ronda 17+18 en la VM.

El dictamen escaló correctamente a Claude (logro de ronda 17/18) PERO:

  • BB (CRÍTICO) — El usuario seleccionó "DISPENSARIO MEDICO" (régimen
    militar) en el dropdown, pero la glosa empezaba con "SALUD TOTAL:".
    El motor cargó el contrato militar 440-DIGSA/DMBUG y normas de FF.MM.
    (Decreto 1795/2000, Acuerdo 002/2001 CSSFFMM) para una glosa de EPS
    contributiva → alucinación total. Decisión del usuario: priorizar el
    texto de la glosa + alertar.
  • CC — El verificador marcaba "Sentencia T-121/2015" como
    NORMA_INEXISTENTE aunque SÍ está en el corpus. Causa: _buscar_clave_norma
    generaba candidatos snake_case (sentencia_121_2015) pero el corpus usa
    upper-words (SENTENCIA T-121 DE 2015). Nunca matcheaba.
  • DD — El campo "Servicio objetado" salió con el placeholder neutro
    concatenado: "HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS, el procedimiento
    facturado según historia clínica".
"""

from app.services.citation_verifier import _buscar_clave_norma, verificar_citas
from app.services.glosa_ia_prompts import (
    _normalizar_eps_para_comparar,
    resolver_eps_efectiva,
)
from app.services.glosa_service import _limpiar_placeholder_servicio
from app.services.normativa_completa import _TODAS_LAS_NORMAS


class TestBugBBDropdownVsTexto:
    def test_dropdown_militar_vs_texto_salud_total_prioriza_texto(self):
        # Caso real 30-jun
        glosa = (
            "SALUD TOTAL: Se objeta integralmente la atención. La paciente "
            "debió ser remitida a la red especializada de Salud Total."
        )
        eps, corregido, alerta = resolver_eps_efectiva("DISPENSARIO MEDICO", glosa)
        assert corregido is True
        assert "SALUD TOTAL" in eps.upper()
        assert "DISPENSARIO MEDICO" not in eps.upper()
        assert alerta  # debe haber mensaje de alerta

    def test_dropdown_coincide_con_texto_no_corrige(self):
        glosa = "SALUD TOTAL: Se objeta la atención."
        eps, corregido, alerta = resolver_eps_efectiva("SALUD TOTAL EPS", glosa)
        assert corregido is False
        assert alerta == ""

    def test_dropdown_generico_usa_texto_sin_alerta(self):
        # OTRA / SIN DEFINIR + texto con EPS → usa texto, sin alerta ruidosa
        glosa = "SALUD TOTAL: Se objeta la atención."
        eps, corregido, alerta = resolver_eps_efectiva("OTRA / SIN DEFINIR", glosa)
        assert corregido is True
        assert "SALUD TOTAL" in eps.upper()
        assert alerta == ""  # genérico no necesita alerta

    def test_texto_sin_eps_conocida_respeta_dropdown(self):
        glosa = "Se objeta la tarifa aplicada sin más detalle."
        eps, corregido, alerta = resolver_eps_efectiva("DISPENSARIO MEDICO", glosa)
        assert corregido is False
        assert eps == "DISPENSARIO MEDICO"

    def test_normalizar_eps_quita_sufijos(self):
        assert _normalizar_eps_para_comparar("SALUD TOTAL EPS") == "SALUD TOTAL"
        assert _normalizar_eps_para_comparar("MEDIMÁS EPS-S") == "MEDIMÁS"
        assert _normalizar_eps_para_comparar("Salud Total") == "SALUD TOTAL"

    def test_dos_contributivas_distintas_es_contradiccion(self):
        # dropdown SURA vs texto ECOOPSOS (ambos en la lista de tokens)
        glosa = "ECOOPSOS objeta integralmente el servicio prestado."
        eps, corregido, _ = resolver_eps_efectiva("SURA EPS", glosa)
        assert corregido is True
        assert "ECOOPSOS" in eps.upper()


class TestBugCCSentenciaT121:
    def test_t121_2015_se_encuentra_en_corpus(self):
        # El corpus tiene la sentencia
        assert "SENTENCIA T-121 DE 2015" in _TODAS_LAS_NORMAS

    def test_buscar_clave_norma_encuentra_t121(self):
        clave = _buscar_clave_norma("t", "121", "2015", _TODAS_LAS_NORMAS)
        assert clave == "SENTENCIA T-121 DE 2015"

    def test_verificar_citas_no_marca_t121_inexistente(self):
        html = "<div>la sentencia T-121/2015 establece que las GPC son recomendativas</div>"
        res = verificar_citas(html)
        inexistentes = [i for i in res["issues"] if "T-121" in i.get("cita", "")]
        assert len(inexistentes) == 0

    def test_su1023_2001_tambien_se_encuentra(self):
        # SU-1023/2001 también está en el corpus, formato con guión
        if "SENTENCIA SU-1023 DE 2001" in _TODAS_LAS_NORMAS:
            clave = _buscar_clave_norma("su", "1023", "2001", _TODAS_LAS_NORMAS)
            assert clave == "SENTENCIA SU-1023 DE 2001"

    def test_t760_2008_sigue_valida(self):
        # Regresión: T-760/2008 (la más citada) debe seguir matcheando
        clave = _buscar_clave_norma("t", "760", "2008", _TODAS_LAS_NORMAS)
        assert clave is not None

    def test_sentencia_realmente_inexistente_sigue_marcada(self):
        # Una sentencia que NO existe debe seguir marcándose
        html = "<div>la sentencia T-9999/2099 dispone algo</div>"
        res = verificar_citas(html)
        inexistentes = [i for i in res["issues"] if "T-9999" in i.get("cita", "")]
        assert len(inexistentes) >= 1


class TestBugDDPlaceholderServicio:
    def test_placeholder_concatenado_se_quita(self):
        s = (
            "HOSPITALIZACIÓN PSIQUIÁTRICA CON TERAPIA DE ESTIMULACIÓN MAGNÉTICA "
            "TRANSCRANEAL (TMS), el procedimiento facturado según historia clínica"
        )
        resultado = _limpiar_placeholder_servicio(s)
        assert "procedimiento facturado según historia clínica" not in resultado.lower()
        assert "HOSPITALIZACIÓN PSIQUIÁTRICA" in resultado
        assert "TMS" in resultado

    def test_placeholder_medicamento_variante(self):
        s = "RITUXIMAB 500MG, el medicamento facturado según historia clínica"
        resultado = _limpiar_placeholder_servicio(s)
        assert "medicamento facturado según historia clínica" not in resultado.lower()
        assert "RITUXIMAB" in resultado

    def test_servicio_solo_placeholder_se_conserva(self):
        # Si el servicio ES solo el placeholder (sin descripción real),
        # no hay nada que rescatar → conservar
        s = "el procedimiento facturado según historia clínica"
        resultado = _limpiar_placeholder_servicio(s)
        assert resultado == s

    def test_servicio_normal_intacto(self):
        s = "IMPLANTE COCLEAR BILATERAL MED-EL SYNCHRONY 2"
        resultado = _limpiar_placeholder_servicio(s)
        assert resultado == s

    def test_servicio_vacio_no_rompe(self):
        assert _limpiar_placeholder_servicio("") == ""


class TestRegresionRondaAnteriores:
    def test_ronda18_urgencias_electivos_intacto(self):
        from app.services.glosa_service import _RE_NO_ES_URGENCIA

        assert _RE_NO_ES_URGENCIA.search("implante coclear bilateral")

    def test_ronda18_cache_version_intacto(self):
        from app.services.glosa_service import _PROMPT_CACHE_VERSION

        assert "r18" in _PROMPT_CACHE_VERSION

    def test_ronda17_routing_compartido_intacto(self):
        from app.services.routing_complejidad import detectar_complejidad_critica

        r = detectar_complejidad_critica(texto_glosa="terapia TMS para esquizofrenia")
        assert r.es_complejo is True
