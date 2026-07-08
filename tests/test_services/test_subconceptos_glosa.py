"""Tests del detector concepto×concepto.

Caso real SALUD TOTAL TMS (30-jun-2026): una glosa con UN código (AU0301)
objetaba 5 conceptos en su texto — (1) TMS no-PBS, (2) 22 días, (3)
autorización, sanción 10%, acompañamiento familiar — y el motor respondía
en bloque omitiendo varios. En auditoría, callar = aceptar.

Este módulo detecta los sub-conceptos para forzar refutación de cada uno.
NO confundir con multi-código (varios CÓDIGOS de glosa); aquí es UN código
con varios CONCEPTOS.
"""

from app.services.subconceptos_glosa import (
    auditar_subconceptos_respondidos,
    bloque_subconceptos_para_prompt,
    detectar_subconceptos,
)

GLOSA_SALUD_TOTAL = (
    "SALUD TOTAL: Se objeta integralmente la atención por las siguientes "
    "razones: (1) la terapia de Estimulación Magnética Transcraneal (TMS) NO "
    "se encuentra dentro del PBS, conforme a la Resolución 2292 de 2021; "
    "(2) la hospitalización psiquiátrica de 22 días excede los lineamientos "
    "de pertinencia, máximo recomendado 14 días; (3) la atención inicial NO "
    "fue tramitada vía solicitud de autorización previa (AU0301). SE APLICA "
    "SANCIÓN DEL 10% AL VALOR FACTURADO. Adicionalmente, se objeta la "
    "cobertura del acompañamiento familiar protocolizado por no estar "
    "incluido en el PBS."
)


class TestDetectarSubconceptos:
    def test_caso_salud_total_detecta_cinco(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        # 3 numerados + sanción + acompañamiento = 5
        assert len(subs) == 5

    def test_numerados_correctos(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        ids = [s["id"] for s in subs]
        assert "1" in ids and "2" in ids and "3" in ids

    def test_concepto_suelto_sancion_detectado(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        resumenes = " ".join(s["resumen"].lower() for s in subs)
        assert "sanción" in resumenes or "sancion" in resumenes.lower()

    def test_concepto_suelto_acompanamiento_detectado(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        resumenes = " ".join(s["resumen"].lower() for s in subs)
        assert "acompañamiento" in resumenes or "cobertura" in resumenes

    def test_no_dobla_concepto_numerado_con_marcador_interno(self):
        # "NO está en PBS" del concepto (1) NO debe crear un sub-concepto
        # aparte (es parte del (1), no uno nuevo).
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        # No debe haber 6+ (sería el falso positivo del NO-PBS interno)
        assert len(subs) == 5

    def test_resumen_no_corta_a_mitad_de_palabra(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        # El resumen del (1) debe empezar con "la terapia" completo
        s1 = next(s for s in subs if s["id"] == "1")
        assert s1["resumen"].startswith("la terapia")

    def test_glosa_concepto_unico_no_detecta(self):
        simple = "TA0201 TARIFA NO PACTADA EN CONTRATO, se reconoce SOAT pleno."
        assert detectar_subconceptos(simple) == []

    def test_glosa_vacia(self):
        assert detectar_subconceptos("") == []
        assert detectar_subconceptos(None) == []

    def test_romanos(self):
        glosa = (
            "(I) la pertinencia del procedimiento es cuestionable; "
            "(II) la tarifa aplicada excede lo pactado en el contrato; "
            "(III) los soportes no fueron adjuntados correctamente."
        )
        subs = detectar_subconceptos(glosa)
        assert len(subs) >= 3


class TestBloquePrompt:
    def test_bloque_lista_cada_concepto(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        bloque = bloque_subconceptos_para_prompt(subs)
        assert "REFUTACIÓN OBLIGATORIA" in bloque
        assert "5 conceptos" in bloque
        # debe enumerar (1)..(5)
        for n in range(1, 6):
            assert f"({n})" in bloque

    def test_bloque_vacio_si_menos_de_dos(self):
        assert bloque_subconceptos_para_prompt([]) == ""
        assert bloque_subconceptos_para_prompt([{"id": "1", "resumen": "x", "texto": "x"}]) == ""

    def test_bloque_advierte_callar_es_aceptar(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        bloque = bloque_subconceptos_para_prompt(subs)
        assert "ACEPTARLO" in bloque or "aceptarlo" in bloque.lower()


class TestAuditorPostValidador:
    def test_detecta_conceptos_omitidos(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        # Dictamen que solo respondió autorización y sanción
        dictamen = (
            "ESE HUS no acepta la glosa por concepto de autorización previa. "
            "la sanción del 10% es improcedente por vicio de competencia."
        )
        ok, omitidos = auditar_subconceptos_respondidos(dictamen, subs)
        assert ok is False
        # TMS, 22 días y acompañamiento quedaron sin responder
        assert len(omitidos) >= 2

    def test_dictamen_completo_no_omite(self):
        subs = detectar_subconceptos(GLOSA_SALUD_TOTAL)
        dictamen = (
            "ESE HUS responde: la TMS es pertinente y cubierta; los 22 días "
            "de hospitalización están justificados clínicamente; la "
            "autorización previa no aplica en urgencias; la sanción del 10% "
            "es improcedente; el acompañamiento familiar es parte integral "
            "del tratamiento psiquiátrico."
        )
        ok, omitidos = auditar_subconceptos_respondidos(dictamen, subs)
        # TMS, hospitalización/días, autorización, sanción, acompañamiento:
        # todos mencionados.
        assert len(omitidos) <= 1  # tolerancia a 1 por heurística

    def test_auditor_con_menos_de_dos_pasa(self):
        ok, omitidos = auditar_subconceptos_respondidos("dictamen", [])
        assert ok is True
        assert omitidos == []


class TestBugCareceFacultad:
    def test_verbo_carece_elidido_se_repara(self):
        from app.services.glosa_service import _neutralizar_alucinaciones_prompt

        texto = "la entidad pagadora de facultad sancionatoria sobre el prestador"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "carece de facultad sancionatoria" in resultado.lower()

    def test_eps_de_facultad_punitiva(self):
        from app.services.glosa_service import _neutralizar_alucinaciones_prompt

        texto = "la EPS de facultad punitiva sobre la IPS"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "carece de facultad punitiva" in resultado.lower()
