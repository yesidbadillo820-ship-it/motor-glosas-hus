"""Tests de regresión ronda 12 (23-jun-2026) — 3 bugs críticos del dictamen.

Evidencia: Yesid pegó 6 dictámenes del motor con casos difíciles ("medicamento
huérfano + MIPRES vencido", "ARL concausa psiquiátrica", "TEA tutela vs
RIPS", "tarifa SOAT homologación", "evento adverso prevenible", "kit Stryker
INVIMA vencido"). Los 6 mostraron los mismos 3 bugs críticos:

  A. La IA confunde NÚMEROS DE NORMA con CUPS de procedimiento:
     "CUPS 1885" (era Resolución 1885), "CUPS 1295" (era Decreto 1295),
     "CUPS 4747" (era Decreto 4747), "CUPS 1011", "CUPS 1887", "CUPS 2284".

  B. PLACEHOLDERS sin sustituir aparecen en el dictamen final:
     "EL código la glosa aplicada/A", "GLOSA N/A", "CUPS LA FACTURA",
     "OTRA / SIN DEFINIR".

  C. TRUNCAMIENTO abrupto: el dictamen termina a mitad de oración por max
     tokens insuficiente: "...SE DEBE TENER EN CUENTA QUE" / "...LA GLOSA
     POR $4." cuando el modelo no es razonador pero la respuesta es larga.
"""

from app.services.glosa_service import (
    _GROQ_MAX_TOKENS,
    _neutralizar_alucinaciones_prompt,
    _termina_completo,
)
from app.services.plantilla_service import PlantillaService


# ─────────────────────────────────────────────────────────────────────
# Bug A — La IA confunde número de norma con CUPS
# ─────────────────────────────────────────────────────────────────────


class TestBugACupsConfundidoConNorma:
    def test_cups_1011_decreto_se_neutraliza(self):
        # Caso 5 (evento adverso): "PROCEDIMIENTO FACTURADO BAJO EL CUPS 1011"
        # — el 1011 era el Decreto 1011 de 2006 SOGCS que la EPS citó.
        texto = "PROCEDIMIENTO FACTURADO BAJO EL CUPS 1011, EVENTO ADVERSO"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1011" not in resultado
        assert "procedimiento facturado" in resultado.lower()

    def test_cups_1295_decreto_arl_se_neutraliza(self):
        # Caso 2 (ARL): "PROCEDIMIENTO FACTURADO BAJO EL CUPS 1295" — 1295
        # era Decreto 1295 de 1994 (Sistema de Riesgos Laborales).
        texto = "El procedimiento facturado bajo el CUPS 1295 corresponde a UCI"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1295" not in resultado

    def test_cups_4747_decreto_se_neutraliza(self):
        # Caso 3 (TEA): "TERAPIA ABA, CUPS 4747" — Decreto 4747 de 2007.
        texto = "Terapia ABA para niño con TEA, CUPS 4747, valor $34M"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 4747" not in resultado

    def test_cups_1885_resolucion_mipres_se_neutraliza(self):
        # Caso 1 (Cerezyme): "ADMINISTRACIÓN DE IMIGLUCERASA CON CUPS 1885" —
        # 1885 era Resolución 1885 de 2018 (MIPRES).
        texto = "ADMINISTRACIÓN DE IMIGLUCERASA (CEREZYME) CON CUPS 1885"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1885" not in resultado

    def test_cups_2284_resolucion_se_neutraliza(self):
        # Caso 7 (Stryker): "PROCEDIMIENTO FACTURADO BAJO EL CUPS 2284" —
        # 2284 era Resolución 2284 de 2023 (transparencia cadena suministro).
        texto = "Craneotomía bajo el CUPS 2284 con kit de neuronavegación"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 2284" not in resultado

    def test_cups_1887_anio_norma_se_neutraliza(self):
        # Caso 6 (COOSALUD): "SERVICIO CON CUPS 1887" — 1887 era el AÑO de
        # la Ley 153 de 1887 que la EPS citó.
        texto = "EL SERVICIO CON CUPS 1887 ES INCORRECTO"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1887" not in resultado

    def test_cups_real_de_6_digitos_NO_se_toca(self):
        # No queremos pisar CUPS REALES (que tienen 5-7 dígitos).
        texto = "consulta médica con CUPS 890201 facturada por $50.000"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "890201" in resultado

    def test_cups_alfanumerico_NO_se_toca(self):
        # CUPS reales como 'FMQ2123', '890388H' tienen letras — no son
        # confundibles con normas. NO los pisamos.
        texto = "kit FMQ2123 reembolsable bajo CUPS 890388H"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "FMQ2123" in resultado
        assert "890388H" in resultado

    def test_codigo_cups_con_decreto_se_neutraliza(self):
        # Variante "CÓDIGO CUPS 1011" (no solo "CUPS 1011" pelado).
        texto = "El CÓDIGO CUPS 1011 es irreal en este caso"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CÓDIGO CUPS 1011" not in resultado
        assert "CUPS 1011" not in resultado


# ─────────────────────────────────────────────────────────────────────
# Bug B — Placeholders sin sustituir
# ─────────────────────────────────────────────────────────────────────


class TestBugBPlaceholdersSinSustituir:
    def test_cola_slash_letra_se_elimina(self):
        # Caso 2 + 3 + 5: "el código de la glosa aplicada/A" — el "/A" era
        # cola del placeholder "CÓDIGO YX/A" que el sanitizador anterior
        # consumía "YX" pero dejaba "/A" suelto.
        texto = "Se solicita el levantamiento de el código de la glosa aplicada/A"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "/A" not in resultado
        assert "el código de la glosa aplicada" in resultado.lower()

    def test_cola_slash_letra_procedimiento_facturado(self):
        texto = "Se reconoce el procedimiento facturado/B según contrato"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "/B" not in resultado

    def test_doble_articulo_EL_el_se_corrige(self):
        # "SOBRE EL el código de la glosa aplicada" — el "EL" mayúsculo es
        # residuo de "SOBRE EL CÓDIGO YX" después del reemplazo que dejó
        # la frase en minúsculas.
        texto = "NO ACEPTA LA GLOSA SOBRE EL el código de la glosa aplicada"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "EL el" not in resultado
        assert "el el" not in resultado.lower()

    def test_cups_la_factura_se_normaliza(self):
        # Caso 4: "PROCEDIMIENTO FACTURADO BAJO EL CUPS LA FACTURA" —
        # placeholder literal del template "CUPS {{NUMERO_FACTURA}}" mal
        # contextualizado.
        texto = "BAJO EL CUPS LA FACTURA del paciente"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS LA FACTURA" not in resultado

    def test_glosa_N_A_se_normaliza(self):
        # "LEVANTAMIENTO LA GLOSA N/A" — default literal de codigo_glosa.
        texto = "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA N/A"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "GLOSA N/A" not in resultado
        assert "N/A" not in resultado

    def test_plantilla_codigo_glosa_vacio_no_pone_NA(self):
        # plantilla_service.py: default ya no es "N/A" sino frase contextual.
        svc = PlantillaService()
        resultado = svc.resolver_variables(
            "Glosa {{CODIGO_GLOSA}} por valor {{VALOR_OBJETADO}}",
            {"valor_objetado": 1500000},
        )
        assert "N/A" not in resultado
        assert "el código de la glosa aplicada" in resultado

    def test_plantilla_cups_vacio_no_pone_NA(self):
        svc = PlantillaService()
        resultado = svc.resolver_variables(
            "Servicio con CUPS {{CUPS}} prestado",
            {},
        )
        assert "CUPS N/A" not in resultado
        assert "el procedimiento facturado" in resultado

    def test_plantilla_eps_vacio_dice_la_eps(self):
        svc = PlantillaService()
        resultado = svc.resolver_variables(
            "La entidad pagadora {{EPS}} objeta",
            {},
        )
        assert "{{EPS}}" not in resultado
        assert "la eps" in resultado.lower()


# ─────────────────────────────────────────────────────────────────────
# Bug C — Truncamiento abrupto
# ─────────────────────────────────────────────────────────────────────


class TestBugCTruncamiento:
    def test_groq_max_tokens_subido_a_5000(self):
        # Antes era 3000 (insuficiente para dictámenes multi-norma).
        assert _GROQ_MAX_TOKENS >= 5000, (
            f"_GROQ_MAX_TOKENS={_GROQ_MAX_TOKENS}, debería ser ≥5000 desde ronda 12"
        )

    def test_termina_completo_con_punto_final(self):
        assert _termina_completo("Se solicita el levantamiento de la glosa.")
        assert _termina_completo("Solicita el reconocimiento integro.\n\n  ")

    def test_termina_completo_con_signo_cierre(self):
        assert _termina_completo("Levantamiento solicitado!")
        assert _termina_completo("¿Aplica el art. 168?")
        assert _termina_completo("Se cita la norma »")

    def test_termina_completo_con_html_cerrado(self):
        # Dictámenes en HTML que cierran con </p> o </div>
        assert _termina_completo("<p>El dictamen final.</p>")
        assert _termina_completo("<div>texto</div>")

    def test_termina_truncado_a_mitad_oracion(self):
        # Caso 2 real: "...SE DEBE TENER EN CUENTA QUE"
        assert not _termina_completo("...SE DEBE TENER EN CUENTA QUE")
        # Caso 6 real: "...LEVANTAMIENTO DE LA GLOSA POR $4."
        assert not _termina_completo("Se solicita el levantamiento de la glosa por $4.")

    def test_termina_truncado_con_dollar_solo(self):
        assert not _termina_completo("Por valor de $")

    def test_termina_truncado_con_conector(self):
        # Conector colgado (sin punto final detrás)
        assert not _termina_completo("Razón por la cual procede el levantamiento de")
        assert not _termina_completo("Conforme al art. 177 Ley 100 que")

    def test_termina_completo_texto_vacio(self):
        # Texto vacío se considera "no truncado" — el flujo upstream lo
        # detecta como error separado, no como truncamiento.
        assert _termina_completo("")
        assert _termina_completo("   \n  ")


# ─────────────────────────────────────────────────────────────────────
# Regresión: los fixes anteriores (ronda 11) siguen funcionando
# ─────────────────────────────────────────────────────────────────────


class TestRegresionRonda11SiguenAplicandose:
    def test_dolar_1_millon_sigue_neutralizado(self):
        texto = "FACTURADO POR $1.000.000 según expediente"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "$1.000.000" not in resultado

    def test_cups_1234_sigue_neutralizado(self):
        texto = "Con CUPS 1234 prestado al paciente"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1234" not in resultado

    def test_resolucion_2641_2024_sigue_neutralizada(self):
        texto = "Conforme a la Resolución 2641 de 2024 art. 5"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "Resolución 2641 de 2024" not in resultado
