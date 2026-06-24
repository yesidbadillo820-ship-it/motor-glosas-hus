"""Tests de regresión ronda 13 (24-jun-2026) — 6 bugs de comportamiento IA.

Yesid pegó otra ronda de dictámenes después de mergeado ronda 12. Detectó
que los 3 bugs críticos previos (CUPS=norma, placeholders, truncamiento) sí
se arreglaron — pero aparecieron / persisten estos 6 bugs de calidad de
argumentación:

  J. ALUCINACIÓN DE VALOR (NUEVO + crítico): cuando el usuario NO le pasa
     valor_objetado, la IA inventa cifras "$950.000", "$1.500.000", basándose
     en su conocimiento general de tarifas. Ejemplo real (24-jun): glosa de
     ecografía Doppler obstétrica sin valor en el input → dictamen dice
     "RESPECTO DEL SERVICIO FACTURADO POR $950.000" — número que NUNCA
     apareció en el texto que el usuario pegó. Esto le saca pinta al
     documento porque la EPS desestima como "no soportado en factura".

  D. ART. 168 LEY 100 COMO MULETILLA: "atención inicial de urgencias" se
     invocaba para defender glosas que NO eran urgencias (terapia ABA
     crónica, UCI 18 días ortopédica, terapia enzimática Cerezyme,
     ecografía Doppler obstétrica electiva).

  G. ART. 177 LEY 100 COMO CITA DE RELLENO: "movilizar recursos para POS"
     aparecía en 5 de 6 casos donde el debate NO era obligación financiera
     EPS (tarifa, pertinencia, evento adverso, ARL).

  F. EVENTO ADVERSO PREVENIBLE — aceptación tácita: la IA decía "la
     clasificación como prevenible no exime de pago" en vez de NEGAR la
     prevenibilidad (que es la defensa correcta).

  H. ARL VS EPS: en glosas de ARL la IA usaba Ley 100 / Ley 1438 (régimen
     EPS) cuando debía citar Decreto 1295/94, Ley 1562/2012, Decreto
     1072/2015, Decreto 780/2016 (régimen riesgos laborales).

  I. AUTO-DETECCIÓN DE EPS: cuando el usuario dejaba el dropdown en
     "OTRA / SIN DEFINIR" pero el texto sí mencionaba la EPS ("La EPS
     Sanitas glosa...", "La ARL Bolívar..."), la IA no usaba el nombre
     real sino la cadena genérica del dropdown.
"""

from app.services.glosa_service import (
    _conjunto_digitos_legitimos,
    _neutralizar_art_168_fuera_de_contexto,
    _neutralizar_art_177_relleno,
    _neutralizar_valores_inventados,
    _normalizar_digitos,
    _refutar_evento_adverso_prevenible,
)
from app.services.glosa_ia_prompts import (
    REGIMEN_ESPECIAL,
    _detectar_pagador_en_texto,
    _detectar_regimen_especial,
    _es_pagador_arl,
)


# ─────────────────────────────────────────────────────────────────────
# Bug J — Alucinación de valor (más crítico)
# ─────────────────────────────────────────────────────────────────────


class TestBugJValorInventado:
    def test_valor_inventado_sin_input_se_neutraliza(self):
        # Caso real 24-jun: usuario no aportó valor, dictamen dice $950.000
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN "
            "SOBRE EL SERVICIO DE ECOGRAFÍA DOPPLER OBSTÉTRICA, INTERPUESTA "
            "POR DISPENSARIO MÉDICO, RESPECTO DEL SERVICIO FACTURADO POR "
            "$950.000, CONFORME AL CONTRATO 440-DIGSA/DMBUG-2025."
        )
        texto_input = "MVC EN ECOGRAFIA DOPPLER OBSTETRICA NO HAY CONTRATO NI ACUERDO DE TARIFAS"
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="",
            texto_input_usuario=texto_input,
        )
        assert "$950.000" not in resultado
        assert "el valor objetado consignado en el expediente" in resultado.lower()

    def test_valor_real_del_input_NO_se_toca(self):
        # Si el usuario sí pasó $48.567.300 (caso Cerezyme), respetar.
        dictamen = "La EPS objeta el pago por $48.567.300 facturado al PPL"
        texto_input = "valor $48.567.300 facturado a paciente PPL"
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="48567300",
            texto_input_usuario=texto_input,
        )
        assert "$48.567.300" in resultado

    def test_valor_input_con_formato_distinto_se_respeta(self):
        # Input "48567300", dictamen "$48.567.300" — son la misma cifra
        # con formato distinto. Tolerar.
        dictamen = "valor objetado de $48.567.300"
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="48567300",
            texto_input_usuario="",
        )
        assert "$48.567.300" in resultado

    def test_valor_subcadena_del_input_se_respeta(self):
        # El input dice "12.720.435" y el dictamen menciona "$12.720" — esa
        # subcadena del input legítimo no se considera alucinación.
        dictamen = "diferencia de $12.720 en la liquidación"
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="12720435",
            texto_input_usuario="",
        )
        assert "$12.720" in resultado

    def test_cifra_chica_se_respeta(self):
        # $10, $100 son demasiado chicas para ser tarifas hospitalarias
        # — no las tocamos.
        dictamen = "el copago de $10 no aplica"
        resultado = _neutralizar_valores_inventados(
            dictamen, valor_raw_input="", texto_input_usuario=""
        )
        assert "$10" in resultado

    def test_varios_valores_inventados_se_neutralizan(self):
        # Caso de glosa multi-código donde la IA inventa $500.000 + $1.500.000
        dictamen = "Se objeta $500.000 por consulta y $1.500.000 por hospitalización."
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="",
            texto_input_usuario="UCI ortopédica sin valor en el expediente",
        )
        assert "$500.000" not in resultado
        assert "$1.500.000" not in resultado

    def test_factura_numero_NO_se_neutraliza_como_valor(self):
        # "HUS0000499027" en el input — la IA puede mencionar 499027 sin
        # signo $ y eso no debe contar como alucinación de valor.
        dictamen = "Factura HUS0000499027 sin valor reportado"
        resultado = _neutralizar_valores_inventados(
            dictamen,
            valor_raw_input="",
            texto_input_usuario="",
            extras=("HUS0000499027",),
        )
        # No hay $N en el dictamen, nada que tocar
        assert "499027" in resultado

    def test_normalizar_digitos_quita_signos(self):
        assert _normalizar_digitos("$950.000") == "950000"
        assert _normalizar_digitos("$ 1,500,000") == "1500000"
        assert _normalizar_digitos("48.567.300,00") == "4856730000"
        assert _normalizar_digitos("") == ""
        assert _normalizar_digitos(None) == ""

    def test_conjunto_digitos_legitimos_consolida(self):
        legit = _conjunto_digitos_legitimos(
            "950000",
            "valor objetado $2.359.398 según factura",
            extras=("HUS0000499027", "12720435"),
        )
        # 950000 (valor_raw) + 2359398 (texto) + 12720435 (extras)
        assert "950000" in legit
        assert "2359398" in legit
        assert "12720435" in legit


# ─────────────────────────────────────────────────────────────────────
# Bug D — Art. 168 Ley 100 como muletilla en glosas no-urgencia
# ─────────────────────────────────────────────────────────────────────


class TestBugDArt168FueraContexto:
    def test_terapia_aba_cronica_NO_invoca_art_168(self):
        # Caso 3 real: glosa de terapia ABA crónica para niño con TEA.
        # NO es urgencia. La IA citaba Art. 168 como muletilla.
        dictamen = (
            "EL ART. 168 LEY 100/1993 establece que la atención inicial "
            "de urgencias debe ser prestada en forma obligatoria."
        )
        texto_glosa = (
            "La EPS Sanitas glosa el 100% de 3 meses de terapia ABA para "
            "niño de 5 años con TEA grado 2."
        )
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, texto_glosa)
        assert "168" not in resultado
        assert "normativa de continuidad" in resultado

    def test_terapia_enzimatica_cronica_NO_invoca_art_168(self):
        # Caso 1 real: medicamento huérfano IMIGLUCERASA en hospital.
        dictamen = "Conforme al art. 168 Ley 100/1993 la atención no se condiciona."
        texto_glosa = "IMIGLUCERASA CEREZYME enfermedad de Gaucher tipo III tratamiento crónico"
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, texto_glosa)
        assert "168" not in resultado

    def test_uci_18_dias_ortopedica_NO_invoca_art_168(self):
        # Caso 2 real: 18 días UCI por caída de andamio (ARL).
        dictamen = "Articulo 168 Ley 100 atención inicial de urgencias"
        texto_glosa = "trabajador formal cayó desde andamio, 18 días UCI + 3 cirugías ortopédicas"
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, texto_glosa)
        assert "168" not in resultado

    def test_ecografia_electiva_NO_invoca_art_168(self):
        # Caso 24-jun: ecografía Doppler obstétrica electiva.
        dictamen = "EL ART. 168 DE LA LEY 100/1993 dispone que la atención"
        texto_glosa = "ECOGRAFIA DOPPLER OBSTETRICA con evaluación de circulación placentaria"
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, texto_glosa)
        assert "168" not in resultado

    def test_urgencia_real_SI_conserva_art_168(self):
        # Si la glosa SÍ es de urgencia, Art. 168 sigue siendo válido.
        dictamen = "Art. 168 Ley 100/1993 sobre atención inicial de urgencias"
        texto_glosa = "Paciente ingresó por URGENCIA con código azul tras politraumatismo"
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, texto_glosa)
        assert "168" in resultado  # se conserva la cita

    def test_urgencia_pero_electivo_simultaneo_NO_invoca_art_168(self):
        # Texto contiene "urgencia" pero también "ambulatorio programado"
        # — gana la negación, NO se cita Art. 168.
        dictamen = "El art. 168 Ley 100 aplica"
        texto_glosa = "Servicio ambulatorio programado en urgencia ambulatoria sin internación"
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, texto_glosa)
        assert "168" not in resultado


# ─────────────────────────────────────────────────────────────────────
# Bug G — Art. 177 Ley 100 como cita de relleno
# ─────────────────────────────────────────────────────────────────────


class TestBugGArt177Relleno:
    def test_glosa_tarifaria_NO_invoca_art_177(self):
        # Caso 4 real: glosa de tarifa SOAT homologación.
        dictamen = (
            "Conforme al art. 177 Ley 100/1993 las entidades promotoras de "
            "salud tendrán las siguientes obligaciones: c) MOVILIZAR LOS "
            "RECURSOS PARA EL OTORGAMIENTO DEL PLAN OBLIGATORIO DE SALUD. "
            "Por lo tanto procede el levantamiento."
        )
        texto_glosa = "homologación tarifaria SOAT 2026 UVB con radiocirugía"
        resultado = _neutralizar_art_177_relleno(
            dictamen, texto_glosa=texto_glosa, codigo_glosa="TA0201"
        )
        assert "Art. 177" not in resultado
        assert "ART. 177" not in resultado
        assert "MOVILIZAR" not in resultado.upper()

    def test_glosa_pertinencia_NO_invoca_art_177(self):
        dictamen = "Art. 177 Ley 100/1993 manda a las EPS movilizar recursos para el POS."
        texto_glosa = "Pertinencia clínica de cirugía electiva sin criterio médico"
        resultado = _neutralizar_art_177_relleno(
            dictamen, texto_glosa=texto_glosa, codigo_glosa="PE0801"
        )
        assert "177" not in resultado

    def test_glosa_evento_adverso_NO_invoca_art_177(self):
        dictamen = "Art. 177 Ley 100 dispone movilizar recursos para el POS"
        texto_glosa = "evento adverso prevenible reintervención"
        resultado = _neutralizar_art_177_relleno(
            dictamen, texto_glosa=texto_glosa, codigo_glosa="CL0901"
        )
        assert "177" not in resultado

    def test_glosa_arl_NO_invoca_art_177(self):
        dictamen = "Art. 177 Ley 100 sobre patrimonios autónomos del POS"
        texto_glosa = "ARL Bolívar concausa preexistente riesgos laborales"
        resultado = _neutralizar_art_177_relleno(
            dictamen, texto_glosa=texto_glosa, codigo_glosa="CO0301"
        )
        assert "177" not in resultado

    def test_glosa_cobertura_PBS_SI_invoca_art_177(self):
        # Cuando la glosa SÍ es sobre obligación de cobertura PBS, Art.
        # 177 es relevante. Conservamos.
        dictamen = "Art. 177 Ley 100/1993 manda movilizar los recursos para el POS"
        texto_glosa = "La EPS niega el servicio por estar fuera de PBS y exclusión del plan"
        resultado = _neutralizar_art_177_relleno(
            dictamen, texto_glosa=texto_glosa, codigo_glosa="CO0501"
        )
        assert "177" in resultado

    def test_codigo_SO_conserva_art_177(self):
        # Para código SO* (soportes), Art. 177 está en el SYSTEM_SO por
        # decisión legítima — no lo tocamos solo por código.
        dictamen = "art. 177 Ley 100 movilizar recursos POS"
        texto_glosa = "soportes insuficientes para auditoría de cuentas"
        resultado = _neutralizar_art_177_relleno(
            dictamen, texto_glosa=texto_glosa, codigo_glosa="SO0501"
        )
        # Solo se quita si el TEXTO claramente apunta a debate no-financiero;
        # acá no hay marcadores fuertes → se conserva.
        assert "177" in resultado


# ─────────────────────────────────────────────────────────────────────
# Bug F — Evento adverso prevenible: defensa correcta es NEGAR
# ─────────────────────────────────────────────────────────────────────


class TestBugFEventoAdversoNegar:
    def test_aceptacion_tacita_se_reescribe_a_negacion(self):
        # Caso 5 real: la IA dijo "no exime de pago" en vez de NEGAR la
        # prevenibilidad.
        dictamen = (
            "LA CLASIFICACIÓN DEL EVENTO COMO ADVERSO PREVENIBLE NO EXIME A "
            "LA EPS DE SU RESPONSABILIDAD DE PAGO. Por lo tanto procede."
        )
        texto_glosa = "evento adverso prevenible dehiscencia colorrectal Res. 256 de 2016"
        resultado = _refutar_evento_adverso_prevenible(dictamen, texto_glosa)
        assert "NO EXIME A LA EPS" not in resultado
        assert "NO RECONOCE LA CLASIFICACIÓN UNILATERAL" in resultado
        assert "Decreto 4747/2007 Art. 20" in resultado

    def test_facturabilidad_variante_se_reescribe(self):
        dictamen = (
            "Las normas no excluyen la facturabilidad de los servicios prestados "
            "en casos de complicaciones secundarias."
        )
        texto_glosa = "complicación prevenible evento adverso"
        resultado = _refutar_evento_adverso_prevenible(dictamen, texto_glosa)
        assert "no excluyen la facturabilidad" not in resultado.lower()

    def test_glosa_sin_evento_adverso_NO_se_toca(self):
        # Si la glosa no menciona evento adverso, no aplicamos la regla.
        dictamen = "Conforme a la Ley 100 la atención debe ser garantizada"
        texto_glosa = "Pertinencia clínica de hemograma"
        resultado = _refutar_evento_adverso_prevenible(dictamen, texto_glosa)
        assert resultado == dictamen


# ─────────────────────────────────────────────────────────────────────
# Bug H — ARL: usar Decreto 1295/Ley 1562, NO Ley 100
# ─────────────────────────────────────────────────────────────────────


class TestBugHRegimenARL:
    def test_es_pagador_arl_por_nombre(self):
        assert _es_pagador_arl("POSITIVA", "") is True
        assert _es_pagador_arl("ARL BOLIVAR", "") is True
        assert _es_pagador_arl("ARL SURA", "") is True
        assert _es_pagador_arl("MAPFRE ARL", "") is True

    def test_es_pagador_arl_por_texto(self):
        # EPS=OTRA/SIN DEFINIR pero texto menciona ARL
        assert _es_pagador_arl("OTRA / SIN DEFINIR", "La ARL Bolívar glosa") is True
        assert _es_pagador_arl("", "ARL Sura niega por accidente de trabajo") is True
        assert _es_pagador_arl("", "FURAT radicado el 5 de mayo") is True
        assert _es_pagador_arl("", "Decreto 1295 de 1994 origen laboral") is True

    def test_no_es_arl_glosa_normal(self):
        assert _es_pagador_arl("FAMISANAR EPS", "consulta pediátrica ambulatoria") is False
        assert _es_pagador_arl("", "Sanitas glosa por tarifa SOAT") is False

    def test_detecta_regimen_arl_desde_texto(self):
        # EPS genérica + texto con ARL → bloque normativo ARL
        bloque = _detectar_regimen_especial(
            "OTRA / SIN DEFINIR",
            "",
            texto_glosa="La ARL Bolívar glosa concausa preexistente",
        )
        assert "RIESGOS LABORALES" in bloque
        assert "Decreto-Ley 1295/1994" in bloque
        assert "Ley 1562/2012" in bloque

    def test_arl_bloque_prohibe_ley_100(self):
        # El bloque ARL instruye explícitamente NO usar Ley 100 / Ley 1438
        bloque = REGIMEN_ESPECIAL["ARL"]
        assert "NO citar Ley 100" in bloque
        assert "Ley 1438" in bloque

    def test_arl_bloque_explica_subrogacion(self):
        # Punto clave para la defensa real: si la ARL alega concausa,
        # debe pagar al hospital y subrogar contra EPS (no prorratear).
        bloque = REGIMEN_ESPECIAL["ARL"]
        assert "subrogarse" in bloque.lower() or "subrogación" in bloque.lower()
        assert "100%" in bloque

    def test_eps_sanitas_NO_dispara_arl(self):
        bloque = _detectar_regimen_especial(
            "SANITAS",
            "EPS CONTRIBUTIVO",
            texto_glosa="Glosa por terapia ABA",
        )
        # Sanitas como EPS común no debe disparar ARL
        assert "RIESGOS LABORALES" not in bloque


# ─────────────────────────────────────────────────────────────────────
# Bug I — Auto-detección de EPS desde texto cuando dropdown es genérico
# ─────────────────────────────────────────────────────────────────────


class TestBugIAutoDeteccionEPS:
    def test_detecta_sanitas_en_texto(self):
        assert _detectar_pagador_en_texto("La EPS Sanitas glosa el 100%") == "SANITAS"

    def test_detecta_compensar_en_texto(self):
        assert (
            _detectar_pagador_en_texto("EPS COMPENSAR niega cobertura del medicamento")
            == "COMPENSAR"
        )

    def test_detecta_coosalud_en_texto(self):
        assert _detectar_pagador_en_texto("La EPS Coosalud ratifica glosa") == "COOSALUD"

    def test_detecta_arl_bolivar_en_texto(self):
        assert (
            _detectar_pagador_en_texto("La ARL Bolívar glosa el 100% de la factura")
            == "ARL BOLÍVAR"
        )

    def test_detecta_nueva_eps_en_texto(self):
        assert _detectar_pagador_en_texto("Nueva EPS objeta por radicación") == "NUEVA EPS"

    def test_detecta_medimas_con_o_sin_tilde(self):
        assert _detectar_pagador_en_texto("La EPS Medimas glosa") == "MEDIMÁS"
        assert _detectar_pagador_en_texto("La EPS Medimás glosa") == "MEDIMÁS"

    def test_detecta_salud_total_en_texto(self):
        assert _detectar_pagador_en_texto("La EPS Salud Total glosa $156M") == "SALUD TOTAL EPS"

    def test_detecta_dmbug_dispensario_completo(self):
        # Forma larga del DMBUG (caso real DGH)
        assert (
            _detectar_pagador_en_texto(
                "DIRECCION DE SANIDAD EJERCITO DISPENSARIO MEDICO BUCARAMANGA"
            )
            == "DMBUG"
        )

    def test_detecta_fomag_o_magisterio(self):
        assert _detectar_pagador_en_texto("FIDUCIARIA PREVISORA FOMAG") == "FOMAG"
        assert _detectar_pagador_en_texto("MAGISTERIO") == "FOMAG"

    def test_texto_sin_eps_conocida_devuelve_vacio(self):
        assert _detectar_pagador_en_texto("Glosa por tarifa sin entidad específica") == ""
        assert _detectar_pagador_en_texto("") == ""
        assert _detectar_pagador_en_texto(None) == ""


# ─────────────────────────────────────────────────────────────────────
# Regresión: los sanitizers de ronda 11 + 12 siguen funcionando
# ─────────────────────────────────────────────────────────────────────


class TestRegresionRondas11y12:
    def test_ronda11_cups_1234_sigue_neutralizado(self):
        from app.services.glosa_service import _neutralizar_alucinaciones_prompt

        texto = "Con CUPS 1234 prestado al paciente"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1234" not in resultado

    def test_ronda12_cups_1011_sigue_neutralizado(self):
        from app.services.glosa_service import _neutralizar_alucinaciones_prompt

        texto = "PROCEDIMIENTO FACTURADO BAJO EL CUPS 1011"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1011" not in resultado

    def test_ronda12_groq_max_tokens_5000_intacto(self):
        from app.services.glosa_service import _GROQ_MAX_TOKENS

        assert _GROQ_MAX_TOKENS >= 5000

    def test_ronda12_termina_completo_intacto(self):
        from app.services.glosa_service import _termina_completo

        assert _termina_completo("Frase completa.")
        assert not _termina_completo("Frase truncada en")
