"""Tests de regresión ronda 16 (26-jun-2026) — 9 bugs detectados tras ronda 15.

Yesid pegó 3 dictámenes super difíciles (Quemado SURA $487M, Norwood NUEVA
EPS $678M, VIH COMPENSAR $128M). Algunos fixes de ronda 15 funcionaron
(Q v1 citas con introductoria, R v1 dropdown EPS) pero los nuevos casos
expusieron:

  CRÍTICO — Auto-escalación a Claude por COMPLEJIDAD: cuando primary_ai=
            groq el motor NUNCA escalaba a Anthropic ni siquiera con casos
            de $678M. Bug detectado al revisar por qué dictamens super
            difíciles tenían tantas alucinaciones — salían de Llama 4 Scout.
  T       — Aceptación parcial estratégica: regla nueva en prompt para
            aceptar conceptos accesorios <5% del total.
  U       — Sanciones EPS ilegales: la IA aceptaba "sanción del 8%" como
            válido. Regla + sanitizer post-IA por vicio de competencia.
  Q v2    — Citas inventadas en MAYÚSCULAS sin "se cita textualmente"
            introductoria — Q v1 las dejaba pasar.
  B v5    — "el procedimiento facturado el medicamento facturado según
            historia clínica" — concatenación doble post Bug A v4.
  B v6    — Palabra duplicada consecutiva ("aplicada aplicada", "glosa glosa").
  N       — Bloque clínico expandido: Epicel/Norwood/HIV/Hemofilia/Cart-T.
  P v3    — +6 normas al corpus: Res. 13437/1991, Res. 2338/2013, T-385/
            2023, T-970/2014, Auto 037/2024, Auto 116/2024.
  O v3    — Post-validador de instrucciones del gestor: warning si pidió
            "incluir Sentencia T-553/2024" y el dictamen no la contiene.
"""

from app.services.glosa_service import (
    _auditar_instrucciones_gestor,
    _neutralizar_alucinaciones_prompt,
    _rechazar_sancion_eps_ilegal,
)
from app.services.normativa_completa import _TODAS_LAS_NORMAS


class TestBugQv2CitasMayusculasSinIntroductoria:
    def test_clausula_mayusculas_sin_introductoria_se_neutraliza(self):
        # Caso real Quemado SURA: la IA inventó cláusula en MAYÚSCULAS
        dictamen = (
            "CLÁUSULA 7 DEL CONTRATO: 'LA EPS RECONOCERÁ TODOS LOS SERVICIOS "
            "DE QUEMADOS PRESTADOS EN UCI ESPECIALIZADA SEGÚN TARIFA MÁXIMA'."
        )
        resultado = _neutralizar_alucinaciones_prompt(dictamen)
        assert "CLÁUSULA 7 DEL CONTRATO:" not in resultado
        assert "cláusulas contractuales" in resultado.lower()

    def test_articulo_contrato_mayusculas_se_neutraliza(self):
        # Caso Norwood: "ARTÍCULO 12 DEL CONTRATO DISPONE: '...'"
        dictamen = (
            "ARTÍCULO 12 DEL CONTRATO DISPONE: 'EL PRESTADOR SE COMPROMETE "
            "A FACTURAR CONFORME AL MANUAL TARIFARIO SOAT 2026 VIGENTE'."
        )
        resultado = _neutralizar_alucinaciones_prompt(dictamen)
        assert "ARTÍCULO 12 DEL CONTRATO DISPONE:" not in resultado

    def test_resolucion_articulo_cita_inventada(self):
        # Resolución X de Y, Artículo Z: "TEXTO INVENTADO"
        dictamen = (
            'Resolución 2284 de 2023, Artículo 17: "El prestador deberá '
            "mantener una calidad de atención conforme a los estándares "
            'establecidos por el Ministerio".'
        )
        resultado = _neutralizar_alucinaciones_prompt(dictamen)
        # La cita textual inventada debe estar reemplazada por la frase
        # neutra "la normativa vigente aplicable"
        assert "Resolución 2284 de 2023, Artículo 17:" not in resultado


class TestBugBv5ConcatenacionDoble:
    def test_concatenacion_procedimiento_medicamento_se_limpia(self):
        # Caso real post Bug A v4: A v4 sustituyó "CUPS 20235847-2" por
        # "el medicamento facturado según historia clínica" y quedó
        # "el procedimiento facturado el medicamento facturado..."
        texto = (
            "se objeta el procedimiento facturado el medicamento "
            "facturado según historia clínica por valor de $5M"
        )
        resultado = _neutralizar_alucinaciones_prompt(texto)
        # Solo debe quedar la frase de medicamento (la de procedimiento se quita)
        assert "el medicamento facturado según historia clínica" in resultado.lower()
        assert resultado.lower().count("facturado") < texto.lower().count("facturado")

    def test_concatenacion_codigo_cups_procedimiento_se_limpia(self):
        # Variante: "el código CUPS de la factura el procedimiento facturado..."
        texto = (
            "Sobre el código CUPS de la factura el procedimiento facturado "
            "según historia clínica, esta entidad..."
        )
        resultado = _neutralizar_alucinaciones_prompt(texto)
        # No debe quedar la doble concatenación
        assert "el código CUPS de la factura el procedimiento facturado" not in resultado

    def test_duplicado_medicamento_facturado_se_dedupe(self):
        texto = (
            "se aplicó el medicamento facturado según historia clínica "
            "el medicamento facturado según historia clínica conforme"
        )
        resultado = _neutralizar_alucinaciones_prompt(texto)
        # Solo una vez
        assert resultado.lower().count("el medicamento facturado según historia clínica") == 1


class TestBugBv6PalabraDuplicada:
    def test_aplicada_aplicada_se_dedupe(self):
        texto = "la glosa aplicada aplicada por SURA al servicio"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "aplicada aplicada" not in resultado.lower()

    def test_segun_segun_se_dedupe(self):
        texto = "se procede según según el contrato vigente"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "según según" not in resultado.lower()

    def test_siglas_cortas_no_se_tocan(self):
        # "EPS EPS" puede ser nombre legítimo (header de tabla, etc.)
        texto = "EPS EPS Y EPS RESTANTE OBJETAN"  # 3 chars, regex >=4 no aplica
        resultado = _neutralizar_alucinaciones_prompt(texto)
        # No tocamos siglas de 3 chars
        assert "EPS EPS" in resultado

    def test_palabras_normales_intactas(self):
        # No debe romper texto legítimo sin duplicados
        texto = "la entidad pagadora aplicó la glosa conforme al contrato"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert resultado == "la entidad pagadora aplicó la glosa conforme al contrato"


class TestBugUSancionesEPSIlegales:
    def test_glosa_con_sancion_8pct_inyecta_rechazo(self):
        # Caso real Quemado SURA: glosa hablaba de "sanción del 8%"
        glosa = (
            "SE APLICA SANCIÓN DEL 8% AL VALOR FACTURADO POR DEMORA EN "
            "LA RADICACIÓN, CONFORME A CLÁUSULA 12 DEL CONTRATO."
        )
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR TA0201. El servicio "
            "fue prestado conforme a tarifa pactada."
        )
        resultado = _rechazar_sancion_eps_ilegal(dictamen, texto_glosa=glosa)
        # Debe haber inyectado el rechazo por vicio de competencia
        assert resultado != dictamen
        assert (
            "vicio de competencia" in resultado.lower()
            or "facultad sancionatoria" in resultado.lower()
        )

    def test_dictamen_acepta_sancion_se_reescribe(self):
        # La IA aceptó la sanción — debe reescribirse como rechazo
        glosa = "SANCIÓN DEL 12% POR DEMORA EN ENTREGA"
        dictamen = "EL HUS SE AJUSTA A LA SANCIÓN APLICADA POR LA EPS. El servicio fue prestado."
        resultado = _rechazar_sancion_eps_ilegal(dictamen, texto_glosa=glosa)
        assert "SE AJUSTA A LA SANCIÓN" not in resultado
        assert "RECHAZA" in resultado.upper() or "rechaza" in resultado.lower()

    def test_dictamen_que_ya_menciona_competencia_no_se_duplica(self):
        # Idempotencia: si el dictamen ya dice "vicio de competencia",
        # no inyectamos nada nuevo.
        glosa = "SANCIÓN DEL 8%"
        dictamen = (
            "EL HUS RECHAZA LA SANCIÓN POR VICIO DE COMPETENCIA SEGÚN LEY 1438/2011 ARTÍCULO 126."
        )
        resultado = _rechazar_sancion_eps_ilegal(dictamen, texto_glosa=glosa)
        # No debe duplicar el rechazo
        assert resultado.lower().count("vicio de competencia") == 1

    def test_glosa_sin_sancion_no_modifica_dictamen(self):
        # Si la glosa NO habla de sanción, no inyectamos nada
        glosa = "TA0201 TARIFA NO PACTADA EN CONTRATO"
        dictamen = "ESE HUS NO ACEPTA LA GLOSA. El servicio fue prestado a tarifa pactada."
        resultado = _rechazar_sancion_eps_ilegal(dictamen, texto_glosa=glosa)
        assert resultado == dictamen


class TestBugOv3PostValidadorInstrucciones:
    def test_instruccion_cita_t553_no_aparece_se_detecta(self):
        instr = "Incluir la Sentencia T-553/2024 sobre acceso a Cart-T"
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA. El servicio Cart-T es procedente."  # NO incluye T-553/2024
        )
        cumplido, omisiones = _auditar_instrucciones_gestor(dictamen, instrucciones_gestor=instr)
        assert cumplido is False
        assert len(omisiones) >= 1

    def test_instruccion_cita_aparece_cumple(self):
        instr = "Incluir la Sentencia T-553/2024"
        dictamen = "ESE HUS cita la Sentencia T-553/2024 que respalda."
        cumplido, omisiones = _auditar_instrucciones_gestor(dictamen, instrucciones_gestor=instr)
        assert cumplido is True
        assert omisiones == []

    def test_instruccion_vacia_devuelve_cumplido(self):
        cumplido, omisiones = _auditar_instrucciones_gestor("dictamen", "")
        assert cumplido is True
        assert omisiones == []

    def test_instruccion_sin_normas_devuelve_cumplido(self):
        # Instrucción que NO menciona normas específicas (puede ser de estilo)
        instr = "Hacer el dictamen más conciso y directo"
        cumplido, omisiones = _auditar_instrucciones_gestor(
            "dictamen breve", instrucciones_gestor=instr
        )
        assert cumplido is True


class TestBugPv3CorpusExpandido:
    def test_resolucion_13437_1991_decalogo_paciente(self):
        assert "RESOLUCION 13437 DE 1991" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["RESOLUCION 13437 DE 1991"]
        assert "decálogo" in str(norma).lower() or "paciente" in str(norma).lower()

    def test_resolucion_2338_2013_tecnologia_biomedica(self):
        assert "RESOLUCION 2338 DE 2013" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["RESOLUCION 2338 DE 2013"]
        assert "biomédica" in str(norma).lower() or "tecnología" in str(norma).lower()

    def test_sentencia_t385_2023_bilateralidad(self):
        assert "SENTENCIA T-385 DE 2023" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["SENTENCIA T-385 DE 2023"]
        assert (
            "bilateral" in str(norma).lower()
            or "sostenibilidad" in str(norma).lower()
            or "EPS-IPS" in str(norma)
        )

    def test_sentencia_t970_2014_muerte_digna(self):
        assert "SENTENCIA T-970 DE 2014" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["SENTENCIA T-970 DE 2014"]
        assert "muerte digna" in str(norma).lower() or "paliativ" in str(norma).lower()

    def test_auto_037_2024_seguimiento_cart_t(self):
        assert "AUTO 037 DE 2024" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["AUTO 037 DE 2024"]
        assert "CAR-T" in str(norma) or "Cart-T" in str(norma) or "Tisagenlecleucel" in str(norma)

    def test_auto_116_2024_sostenibilidad(self):
        assert "AUTO 116 DE 2024" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["AUTO 116 DE 2024"]
        assert (
            "ADRES" in str(norma)
            or "giro directo" in str(norma).lower()
            or "sostenibilidad" in str(norma).lower()
        )


class TestBloqueClinicoExpandido:
    """Bug N: la regla 8 del system prompt debe mencionar Epicel,
    Norwood, IRIS, hemofilia con inhibidores y Cart-T."""

    def test_system_prompt_menciona_epicel(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "Epicel" in SYSTEM_BASE

    def test_system_prompt_menciona_norwood(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "Norwood" in SYSTEM_BASE

    def test_system_prompt_menciona_iris_post_tarv(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "IRIS" in SYSTEM_BASE or "Reconstitución Inmune" in SYSTEM_BASE

    def test_system_prompt_menciona_hemofilia_inhibidores(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "Hemofilia" in SYSTEM_BASE
        assert "inhibidores" in SYSTEM_BASE.lower()

    def test_system_prompt_menciona_cart_t(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "Cart-T" in SYSTEM_BASE or "CAR-T" in SYSTEM_BASE


class TestBugTAceptacionParcial:
    """Bug T: regla 8.bis en el system prompt sobre aceptación parcial estratégica."""

    def test_system_prompt_menciona_aceptacion_parcial(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "ACEPTACIÓN PARCIAL ESTRATÉGICA" in SYSTEM_BASE
        assert "ACEPTAR_PARCIAL" in SYSTEM_BASE

    def test_system_prompt_menciona_umbral_5pct(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "< 5%" in SYSTEM_BASE or "5%" in SYSTEM_BASE


class TestSancionEPSReglaPrompt:
    """Bug U como REGLA en el system prompt (además del sanitizer)."""

    def test_system_prompt_prohibe_aceptar_sanciones(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "PROHIBIDO ACEPTAR SANCIONES" in SYSTEM_BASE
        assert "VICIO DE COMPETENCIA" in SYSTEM_BASE
        assert "Ley 1438/2011 Art. 126" in SYSTEM_BASE

    def test_system_prompt_menciona_intereses_dtf(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "INTERESES MORATORIOS" in SYSTEM_BASE or "DTF" in SYSTEM_BASE


class TestRegresionRondaAnteriores:
    """Las correcciones de rondas anteriores siguen activas."""

    def test_ronda12_cups_1011_sigue_neutralizado(self):
        texto = "PROCEDIMIENTO BAJO EL CUPS 1011"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1011" not in resultado

    def test_ronda14_codigo_uvb_intacto(self):
        from app.services.glosa_service import _DIGITOS_CONSTANTES_LEGITIMOS

        assert "12110" in _DIGITOS_CONSTANTES_LEGITIMOS

    def test_ronda15_cum_sufijo_se_neutraliza(self):
        # Bug A v4 ronda 15 sigue activo
        texto = "EL CUPS 20235847-2 DEL TISAGENLECLEUCEL"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "20235847-2" not in resultado
