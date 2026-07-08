"""Tests de regresión ronda 14 (25-jun-2026) — 7 bugs detectados tras ronda 13.

Yesid pegó 3 dictámenes más (trasplante hepático $487M, migrante venezolana
Dengue grave $43M, TEVAR aneurisma roto $312M). Los fixes de ronda 12 y 13
están funcionando, pero aparecieron / persisten:

  A v3: CUM y restos de Registro INVIMA confundidos con CUPS.
       "CUPS 19953856" (CUM Tacrolimus), "CUPS 20002174" (CUM Norepinefrina),
       "CUPS 0021987" (fragmento de INVIMA 2023DM-0021987). Mi sanitizer
       ronda 12 cubría 3-4 dígitos puros; estos tienen 7-8 dígitos.

  B v3: nuevos placeholders:
       "LA NUEVA la entidad pagadora LA GLOSA" (residuo entre EPS y plantilla)
       "el manejo clínico el paciente identificado" (falta "de" → "del paciente")
       "NO REQUIERE LA APROBACIÓN PREVIA LA EPS" (falta "de" → "previa de la EPS")

  I v2: la EPS auto-detectada del texto reemplaza el cuerpo pero el HEADER
       de la tabla sigue mostrando "OTRA / SIN DEFINIR".

  K (regresión introducida por ronda 13): el sanitizer Bug J pisaba el
     valor de UVB ($12.110) y otras constantes del prompt que NO son
     alucinaciones — son valores objetivos del Manual SOAT.

  L: dictámenes salen TODO EN MAYÚSCULAS, antitécnico para documento jurídico.

  M+O (en system prompt): IA defendía 100% ciegamente sin reconocer cuando
       la EPS tiene base parcial (caso migrante: la atención sí es del HUS pero
       el pago corresponde al Ente Territorial, NO a una EPS). Omitía
       contraargumentos específicos por nombre (Auto 116/2024, Sentencia T-934).

  P: el verifier marcaba como NORMA_INEXISTENTE Decreto 2493/2004, Decreto
     600/2017, Decreto 4725/2005, Resolución 1885/2018, Acuerdo 256/2001 —
     todas existen realmente.
"""

from app.services.glosa_service import (
    _DIGITOS_CONSTANTES_LEGITIMOS,
    _conjunto_digitos_legitimos,
    _es_sigla_o_codigo,
    _neutralizar_alucinaciones_prompt,
    _neutralizar_valores_inventados,
    _normalizar_mayusculas_sostenidas,
    _sustituir_eps_generica_en_dictamen,
)
from app.services.normativa_completa import _TODAS_LAS_NORMAS


# ─────────────────────────────────────────────────────────────────────
# Bug A v3 — CUM y restos de Registro INVIMA como CUPS
# ─────────────────────────────────────────────────────────────────────


class TestBugAv3CumInvima:
    def test_cum_8_digitos_se_neutraliza(self):
        # Caso real trasplante: "CUPS 19953856" — era CUM Tacrolimus 19953856-3
        texto = "PROCEDIMIENTO FACTURADO BAJO EL CUPS 19953856 SEGUN MIPRES"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 19953856" not in resultado
        assert "procedimiento facturado" in resultado.lower()

    def test_cum_con_sufijo_se_neutraliza_ronda15(self):
        # Ronda 14 dejaba el sufijo "-X" por compat ronda 11. Ronda 15
        # corrigió: TODO CUM (con o sin sufijo) que la IA escribe como
        # CUPS es alucinación de categorización (medicamento ≠ procedimiento).
        # El test viejo de ronda 11 también fue actualizado.
        texto = "EL CUPS 19953856-3 DEL TACROLIMUS"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "19953856-3" not in resultado
        assert "medicamento facturado" in resultado.lower()

    def test_cum_norepinefrina_se_neutraliza(self):
        # Caso real migrante Dengue: "CUPS 20002174"
        texto = "USO DE CUPS 20002174 PARA SOPORTE HEMODINAMICO"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 20002174" not in resultado

    def test_invima_fragment_7_digitos_NO_se_confunde_con_cups(self):
        # Caso TEVAR: "CUPS 0021987" — fragmento de Registro INVIMA
        # 2023DM-0021987. 7 dígitos puros NO es un CUPS válido.
        texto = "CRANEOTOMÍA BAJO EL CUPS 0021987"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 0021987" not in resultado

    def test_cups_real_de_6_digitos_NO_se_pisa(self):
        # CUPS reales 5-6 dígitos: 890201, 882201, 890388 — NO los tocamos
        # (mi regex requiere 7+ dígitos).
        texto = "consulta médica con CUPS 890201"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "890201" in resultado

    def test_cups_alfanumerico_FMQ_intacto(self):
        # CUPS reales alfanuméricos
        texto = "kit FMQ2123 + CUPS 890388H"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "FMQ2123" in resultado
        assert "890388H" in resultado


# ─────────────────────────────────────────────────────────────────────
# Bug B v3 — placeholders nuevas variantes
# ─────────────────────────────────────────────────────────────────────


class TestBugBv3PlaceholdersNuevos:
    def test_la_nueva_la_entidad_pagadora_se_normaliza(self):
        # Caso real trasplante: residuo "LA NUEVA la entidad pagadora LA GLOSA"
        texto = "LA NUEVA EPS la entidad pagadora LA GLOSA CON TRES CAUSALES"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        # El "la entidad pagadora" intermedio se elimina
        assert "la entidad pagadora LA GLOSA" not in resultado
        assert "LA NUEVA EPS" in resultado

    def test_manejo_clinico_el_paciente_se_corrige(self):
        # Caso real migrante: "el manejo clínico el paciente identificado"
        # falta preposición "de" entre "clínico" y "el paciente"
        texto = "el manejo clínico el paciente identificado en el expediente"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "clínico el paciente" not in resultado.lower()
        assert "del paciente" in resultado.lower() or "de el paciente" in resultado.lower()

    def test_previa_la_eps_se_corrige(self):
        # Caso real: "PREVIA LA EPS" sin preposición → "previa de la EPS"
        texto = "NO REQUIERE LA APROBACIÓN PREVIA LA EPS"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "PREVIA LA EPS" not in resultado
        assert "previa de la eps" in resultado.lower()

    def test_entidad_pagadora_duplicada_se_normaliza(self):
        texto = "POR la entidad pagadora la entidad pagadora del trasplante"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        # Solo queda una vez
        assert resultado.lower().count("la entidad pagadora") == 1


# ─────────────────────────────────────────────────────────────────────
# Bug I v2 — Header sigue OTRA / SIN DEFINIR
# ─────────────────────────────────────────────────────────────────────


class TestBugIv2HeaderEPS:
    def test_sustitucion_otra_sin_definir_por_eps_real(self):
        dictamen = "INTERPUESTA POR OTRA / SIN DEFINIR sobre el procedimiento"
        resultado = _sustituir_eps_generica_en_dictamen(dictamen, "FAMISANAR EPS")
        assert "OTRA / SIN DEFINIR" not in resultado
        assert "FAMISANAR EPS" in resultado

    def test_variantes_otra_sin_definir(self):
        # Con espacios alrededor del slash
        for variante in (
            "OTRA / SIN DEFINIR",
            "OTRA/SIN DEFINIR",
            "Otra / Sin Definir",
        ):
            dictamen = f"Por {variante} se objeta"
            resultado = _sustituir_eps_generica_en_dictamen(dictamen, "SANITAS")
            assert variante not in resultado
            assert "SANITAS" in resultado

    def test_sin_eps_detectada_NO_toca_nada(self):
        dictamen = "OTRA / SIN DEFINIR objeta el procedimiento"
        # eps_detectada vacía o genérica → no se toca
        for eps in ("", None, "OTRA / SIN DEFINIR", "OTRA"):
            assert _sustituir_eps_generica_en_dictamen(dictamen, eps) == dictamen

    def test_eps_real_NO_aparece_en_header_se_conserva(self):
        # Si "OTRA / SIN DEFINIR" no aparece, no hay nada que sustituir
        dictamen = "SANITAS objeta el procedimiento"
        resultado = _sustituir_eps_generica_en_dictamen(dictamen, "SANITAS")
        assert resultado == dictamen


# ─────────────────────────────────────────────────────────────────────
# Bug K — Whitelist UVB y otras constantes del prompt
# ─────────────────────────────────────────────────────────────────────


class TestBugKConstantesLegitimas:
    def test_uvb_2026_es_legitimo(self):
        assert "12110" in _DIGITOS_CONSTANTES_LEGITIMOS

    def test_uvb_2025_es_legitimo(self):
        assert "11552" in _DIGITOS_CONSTANTES_LEGITIMOS

    def test_smlv_2026_es_legitimo(self):
        assert "1423500" in _DIGITOS_CONSTANTES_LEGITIMOS

    def test_uvb_en_dictamen_no_se_pisa(self):
        # Caso real TEVAR: "UVB 2026 = $12.110" era constante del prompt
        # — el sanitizer ronda 13 lo pisaba como alucinación.
        dictamen = "Tarifa pactada: SOAT pleno con UVB 2026 = $12.110"
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="",
            texto_input_usuario="glosa sin valor objetado",
        )
        assert "$12.110" in resultado

    def test_conjunto_legitimos_incluye_constantes(self):
        legit = _conjunto_digitos_legitimos("", "", extras=())
        # Aunque el input esté vacío, las constantes del prompt están
        assert "12110" in legit
        assert "11552" in legit
        assert "1423500" in legit


# ─────────────────────────────────────────────────────────────────────
# Bug L — Normalizar mayúsculas sostenidas
# ─────────────────────────────────────────────────────────────────────


class TestBugLMayusculasSostenidas:
    def test_todo_mayusculas_se_normaliza(self):
        dictamen = "ESE HUS NO ACEPTA LA GLOSA APLICADA POR SANITAS."
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        # Sentence case: primer letra mayúscula, resto minúscula
        assert resultado != dictamen
        # Siglas conocidas preservadas
        assert "HUS" in resultado
        assert "ESE" in resultado
        assert "SANITAS" in resultado

    def test_texto_mixto_no_se_toca(self):
        # Si el texto ya está bien formateado (sentence case), no se toca
        dictamen = "El HUS rechaza la glosa por improcedente. La EPS no aporta soportes."
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        assert resultado == dictamen

    def test_siglas_conocidas_se_conservan(self):
        dictamen = "EL ART. 168 LEY 100/1993 ESTABLECE COBERTURA. LA EPS DEBE PAGAR. EL NIT 900.006.037-4 DEL HUS."
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        assert "EPS" in resultado
        assert "NIT" in resultado
        assert "HUS" in resultado

    def test_codigos_glosa_se_conservan(self):
        dictamen = "LA GLOSA CON CÓDIGO TA0201 Y SO0501 ES IMPROCEDENTE."
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        # Códigos alfanuméricos preservados upper
        assert "TA0201" in resultado
        assert "SO0501" in resultado

    def test_es_sigla_o_codigo(self):
        assert _es_sigla_o_codigo("HUS") is True
        assert _es_sigla_o_codigo("EPS") is True
        assert _es_sigla_o_codigo("TA0201") is True
        assert _es_sigla_o_codigo("FMQ2123") is True
        assert _es_sigla_o_codigo("paciente") is False
        assert _es_sigla_o_codigo("glosa") is False
        assert _es_sigla_o_codigo("") is False

    def test_umbral_no_se_dispara_con_pocas_mayusculas(self):
        # Texto donde solo HUS, EPS están en upper — el resto en case
        dictamen = "El HUS responde a la EPS con argumento conforme al art. 168."
        # < 55% uppercase → no se toca
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        assert resultado == dictamen


# ─────────────────────────────────────────────────────────────────────
# Bug P — Corpus normativo expandido
# ─────────────────────────────────────────────────────────────────────


class TestBugPCorpusExpandido:
    def test_decreto_2493_2004_donacion_organos(self):
        assert "DECRETO 2493 DE 2004" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["DECRETO 2493 DE 2004"]
        assert "trasplante" in norma["nombre"].lower() or "trasplante" in str(norma).lower()

    def test_decreto_600_2017_ppl(self):
        assert "DECRETO 600 DE 2017" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["DECRETO 600 DE 2017"]
        assert "PPL" in norma["nombre"] or "ppl" in str(norma).lower()

    def test_decreto_4725_2005_dispositivos(self):
        assert "DECRETO 4725 DE 2005" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["DECRETO 4725 DE 2005"]
        assert "INVIMA" in str(norma) or "dispositivos" in str(norma).lower()

    def test_resolucion_1885_2018_mipres(self):
        # Distinta a la 1885/2024 (cronograma Manual Único)
        assert "RESOLUCION 1885 DE 2018" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["RESOLUCION 1885 DE 2018"]
        assert "MIPRES" in str(norma)

    def test_acuerdo_256_2001_soat(self):
        assert "ACUERDO 256 DE 2001" in _TODAS_LAS_NORMAS

    def test_acuerdo_029_2011_derogado(self):
        assert "ACUERDO 029 DE 2011" in _TODAS_LAS_NORMAS
        # Marcado como NO vigente
        assert _TODAS_LAS_NORMAS["ACUERDO 029 DE 2011"]["vigente"] is False


# ─────────────────────────────────────────────────────────────────────
# Regresión: rondas previas siguen verde
# ─────────────────────────────────────────────────────────────────────


class TestRegresionRondas12y13:
    def test_ronda12_cups_1011_sigue_neutralizado(self):
        # Bug A v1 — debe seguir activo aunque ahora también atrapamos 7-9 dígitos
        texto = "PROCEDIMIENTO BAJO EL CUPS 1011"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1011" not in resultado

    def test_ronda13_valor_inventado_sigue_neutralizado(self):
        # Bug J — valor inventado debe seguir bloqueándose
        dictamen = "FACTURADO POR $950.000 según expediente"
        resultado = _neutralizar_valores_inventados(
            dictamen, valor_raw_input="", texto_input_usuario="doppler sin valor"
        )
        assert "$950.000" not in resultado
