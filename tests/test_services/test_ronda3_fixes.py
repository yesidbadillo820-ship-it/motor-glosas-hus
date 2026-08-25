"""Tests de regresión — RONDA 3 (16-jun-2026).

Cada fix con los textos EXACTOS de la evidencia de los 8 casos de estrés
que el dueño corrió en producción y reportó. Si alguno de estos tests
falla en el futuro, significa que la regresión volvió.
"""

from __future__ import annotations

from app.services.contexto_contractual_enriquecido import es_cups_descartable
from app.services.glosa_service import (
    _limpiar_chain_of_thought,
    _neutralizar_contratos_ajenos,
    _neutralizar_cups_falsos,
    _rellenar_placeholders,
    detectar_fechas_en_texto,
)
from app.utils.parsers_glosa import _extraer_cups_servicio


# ──────────────────────────────────────────────────────────────────────
#  FIX A — chain-of-thought leakage
# ──────────────────────────────────────────────────────────────────────


class TestCotLeakage:
    """qwen3/gpt-oss a veces emiten razonamiento en inglés que se cuela al
    dictamen cuando arg_ia cae al fallback res_ia entero."""

    def test_caso_1_tags_let_me(self):
        """Caso 1 del usuario, AU0301 artroplastia electiva."""
        mal = (
            "tags. Let me go through each section step by step, making sure "
            "all corrections are applied without changing the legal substance.\n"
            "  ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE AUTORIZACIÓN."
        )
        out = _limpiar_chain_of_thought(mal)
        assert "Let me" not in out
        assert "tags." not in out
        assert "ESE HUS NO ACEPTA" in out

    def test_caso_4_changes_alright_xml(self):
        """Caso 4 (COOSALUD): 'changes. Let me draft…Alright, let's…```xml'."""
        mal = (
            "changes. Let me draft each part step by step, making sure each "
            "correction is addressed. Check for the word count after each "
            "addition. Make sure the quotes are properly enclosed and the "
            "clauses are in place. Alright, let's put it all together.\n"
            " ```xml\n\nESE HUS NO ACEPTA LA GLOSA."
        )
        out = _limpiar_chain_of_thought(mal)
        assert "Let me draft" not in out
        assert "```xml" not in out
        assert "Alright" not in out
        assert "Make sure" not in out
        assert "ESE HUS NO ACEPTA" in out

    def test_caso_5_tags_punto_solo(self):
        """Caso 5 (DISPENSARIO): 'tags.' como token aislado."""
        mal = "tags.\nESE HUS NO ACEPTA LA GLOSA."
        out = _limpiar_chain_of_thought(mal)
        assert "tags." not in out
        assert "ESE HUS NO ACEPTA" in out

    def test_no_falso_positivo_espanol(self):
        """Texto legítimo en español NO debe alterarse."""
        bueno = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE "
            "AUTORIZACIÓN (AU0301).\nConforme al artículo 168 de la Ley "
            "100 de 1993, la atención de urgencias no podrá ser "
            "condicionada.\nSe solicita el levantamiento de la glosa."
        )
        out = _limpiar_chain_of_thought(bueno)
        assert out.strip() == bueno.strip()

    def test_texto_vacio(self):
        assert _limpiar_chain_of_thought("") == ""
        assert _limpiar_chain_of_thought(None) is None  # type: ignore


# ──────────────────────────────────────────────────────────────────────
#  FIX B — placeholders crudos ampliados
# ──────────────────────────────────────────────────────────────────────


class TestPlaceholdersAmpliados:
    """Caso 5 ENTREGADO con [ENTIDAD], [VALOR REAL], [DESCRIPCIÓN DEL
    SERVICIO] sin rellenar."""

    def test_caso_5_evidencia_completa(self):
        mal = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE PRESUNTA "
            "DUPLICACIÓN DE FACTURACIÓN, INTERPUESTA POR [ENTIDAD], "
            "RESPECTO DE LOS CÓDIGOS 20260511 FACTURADOS POR [VALOR REAL] "
            "POR EL SERVICIO DE [DESCRIPCIÓN DEL SERVICIO]."
        )
        out = _rellenar_placeholders(
            mal, eps="DISPENSARIO MEDICO", codigo="FA0101", valor="$9.450.000"
        )
        assert "[ENTIDAD]" not in out
        assert "[VALOR REAL]" not in out
        assert "[DESCRIPCIÓN DEL SERVICIO]" not in out

    def test_valor_facturado_y_monto(self):
        """Nuevos placeholders que el modelo ha inventado."""
        mal = "FACTURADO POR [VALOR FACTURADO] correspondiente al [MONTO] del [TIPO DE SERVICIO]."
        out = _rellenar_placeholders(mal, eps="COOSALUD", codigo="TA0201", valor="$8.000.000")
        assert "[VALOR FACTURADO]" not in out
        assert "[MONTO]" not in out
        assert "[TIPO DE SERVICIO]" not in out
        assert "$8.000.000" in out

    def test_fecha_placeholder(self):
        mal = "Notificado el [FECHA] por [ENTIDAD]."
        out = _rellenar_placeholders(mal, eps="NUEVA EPS", codigo="", valor="")
        assert "[FECHA]" not in out
        assert "[ENTIDAD]" not in out


# ──────────────────────────────────────────────────────────────────────
#  FIX C — detección de RATIFICADA en el texto (extemporaneidad)
# ──────────────────────────────────────────────────────────────────────


class TestExtemporaneidadRatificacionTexto:
    """Caso 1: 'Glosa inicial notificada el 10/04/2026 y RATIFICADA por la
    EPS el 15/06/2026' — antes el regex no lo detectaba porque pedía
    'FECHA RECEPCIÓN RATIFICACIÓN:'."""

    def test_caso_1_evidencia_exacta(self):
        texto = "Glosa inicial notificada el 10/04/2026 y RATIFICADA por la EPS el 15/06/2026."
        fechas = detectar_fechas_en_texto(texto)
        assert fechas["fecha_radicacion"] == "2026-04-10"
        assert fechas["fecha_ratificacion"] == "2026-06-15"

    def test_variantes_verbo_ratificar(self):
        casos = [
            (
                "Glosa RADICADA el 01/03/2026, RATIFICADA el 15/05/2026.",
                ("2026-03-01", "2026-05-15"),
            ),
            (
                "La glosa inicial fue notificada el 10/02/2026 y ratificada el 20/04/2026.",
                ("2026-02-10", "2026-04-20"),
            ),
        ]
        for texto, (esp_rad, esp_rat) in casos:
            fechas = detectar_fechas_en_texto(texto)
            assert fechas["fecha_radicacion"] == esp_rad, (
                f"radicación: esperaba {esp_rad}, got {fechas}"
            )
            assert fechas["fecha_ratificacion"] == esp_rat, (
                f"ratificación: esperaba {esp_rat}, got {fechas}"
            )

    def test_no_dispara_sin_fechas(self):
        texto = "Glosa inicial y ratificación posterior, sin fechas precisas."
        fechas = detectar_fechas_en_texto(texto)
        assert fechas["fecha_radicacion"] is None
        assert fechas["fecha_ratificacion"] is None

    def test_compatible_con_formato_viejo(self):
        """Las labels viejas 'Fecha radicación:' siguen funcionando."""
        texto = "Fecha radicación: 2026-03-01. Fecha recepción ratificación: 2026-05-30."
        fechas = detectar_fechas_en_texto(texto)
        assert fechas["fecha_radicacion"] == "2026-03-01"
        assert fechas["fecha_ratificacion"] == "2026-05-30"


# ──────────────────────────────────────────────────────────────────────
#  FIX D — fechas yyyymmdd descartadas como CUPS
# ──────────────────────────────────────────────────────────────────────


class TestCupsYyyymmddDescartado:
    """Caso 4: 'Verificar radicado 20260511 y soporte 4710-2026' → la IA
    escribió 'código CUPS 20260511' (es 11/05/2026, no un CUPS)."""

    def test_yyyymmdd_caso_4(self):
        # 20260511 = 11 de mayo de 2026
        assert es_cups_descartable("20260511") is True
        # 20260518 = 18 de mayo
        assert es_cups_descartable("20260518") is True
        # 20260430 = 30 de abril
        assert es_cups_descartable("20260430") is True

    def test_cups_reales_no_descartados(self):
        # CUPS reales de 6 dígitos (hemograma, BUN, etc.)
        assert es_cups_descartable("890201") is False
        assert es_cups_descartable("390201") is False
        assert es_cups_descartable("903841") is False
        # Código institucional HUS con sufijo
        assert es_cups_descartable("39147B-18") is False
        # FMQ no es prefijo de factura sino código de medicamento institucional
        assert es_cups_descartable("FMQ6296") is False

    def test_yyyymmdd_invalido(self):
        # Mes 13 = no es fecha válida → no se descarta como yyyymmdd
        # (puede ser CUPS legítimo de 8 dígitos)
        assert es_cups_descartable("20261301") is False
        # Día 32
        assert es_cups_descartable("20260532") is False

    def test_extractor_parsers_glosa_yyyymmdd(self):
        """_extraer_cups_servicio también lo descarta (capa hoja paralela)."""
        texto = "Verificar radicado 20260511 y soporte. Servicio 890201."
        cups, _desc = _extraer_cups_servicio(texto)
        # NO debe devolver 20260511; idealmente devuelve 890201 (CUPS real)
        assert cups != "20260511", f"yyyymmdd no debió extraerse: {cups}"


# ──────────────────────────────────────────────────────────────────────
#  FIX E — red final contratos ajenos
# ──────────────────────────────────────────────────────────────────────


class TestContratosAjenos:
    """Caso 5 (DISPENSARIO MEDICO citó 440-DIGSA, el contrato militar)."""

    def test_dispensario_citando_contrato_de_famisanar(self):
        """Glosa con EPS=DISPENSARIO MEDICO citando S-13-1-03-1-04958 (que
        pertenece a FAMISANAR según el catálogo CONTRATOS_HUS)."""
        mal = (
            "Conforme al CONTRATO S-13-1-03-1-04958 cláusula 8.13, "
            "los servicios se cancelan al proveedor."
        )
        out = _neutralizar_contratos_ajenos(mal, eps="DISPENSARIO MEDICO")
        assert "S-13-1-03-1-04958" not in out
        # 06-08-2026: el sintagma va en MAYÚSCULA, como todo el dictamen.
        assert "EL CONTRATO VIGENTE ENTRE LAS PARTES" in out.upper()

    def test_oncologico_caso_2_contratos_ajenos(self):
        """Caso 2 del usuario: EPS oncológico (NUEVA EPS) no es dueño de
        DIGSA/DMBUG, así que esos contratos son ajenos cuando aparecen."""
        # NUEVA EPS no es dueña de 'S-13-1-03-1-04958' (FAMISANAR)
        mal = "Se invoca el CONTRATO S-13-1-03-1-04958 entre las partes."
        out = _neutralizar_contratos_ajenos(mal, eps="NUEVA EPS")
        assert "S-13-1-03-1-04958" not in out

    def test_contrato_correcto_no_se_toca(self):
        """Si la EPS sí es la dueña del contrato, no se modifica."""
        bueno = "Conforme al CONTRATO S-13-1-03-1-04958 cláusula 8.13."
        out = _neutralizar_contratos_ajenos(bueno, eps="FAMISANAR EPS")
        assert "S-13-1-03-1-04958" in out

    def test_sin_eps_no_dispara(self):
        bueno = "Conforme al contrato vigente."
        assert _neutralizar_contratos_ajenos(bueno, eps="") == bueno
        assert _neutralizar_contratos_ajenos(bueno, eps=None) == bueno  # type: ignore


# ──────────────────────────────────────────────────────────────────────
#  FIX F — red final CUPS falsos
# ──────────────────────────────────────────────────────────────────────


class TestCupsFalsos:
    """Caso 4: dictamen escribió 'código CUPS 20260511' (era una fecha)."""

    def test_yyyymmdd_como_cups_neutralizado(self):
        mal = "ESE HUS reconoce el código CUPS 20260511 facturado por COOSALUD."
        out = _neutralizar_cups_falsos(mal)
        assert "20260511" not in out
        assert "facturado facturado" not in out.lower()
        assert "EL PROCEDIMIENTO FACTURADO POR COOSALUD" in out.upper()

    def test_fecha_con_guion_como_cups(self):
        mal = "El CUPS 2026-05-11 corresponde al servicio."
        out = _neutralizar_cups_falsos(mal)
        assert "2026-05-11" not in out
        assert "EL PROCEDIMIENTO FACTURADO" in out.upper()

    def test_hus_como_cups(self):
        mal = "Servicio CUPS HUS00012345 detallado."
        out = _neutralizar_cups_falsos(mal)
        assert "HUS00012345" not in out

    def test_cups_real_no_neutralizado(self):
        """Un CUPS real (6 dígitos sin patrón de fecha) NO se toca."""
        bueno = "El CUPS 890201 corresponde al hemograma."
        out = _neutralizar_cups_falsos(bueno)
        assert "890201" in out

    def test_sin_cambios_si_no_hay_cups_falso(self):
        bueno = "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS."
        assert _neutralizar_cups_falsos(bueno) == bueno


# ──────────────────────────────────────────────────────────────────────
#  FIX G — _llamar_groq_con_retry: log + retry sin reasoning_effort
# ──────────────────────────────────────────────────────────────────────


class TestGroqReasoningEffortRetry:
    """Diagnóstico ronda 3: TODOS los dictámenes salieron en qwen3-32b,
    nunca en gpt-oss-120b. Hipótesis: la API de Groq rechaza
    reasoning_effort con 400. El retry sin ese parámetro destraba gpt-oss
    como primario sin caer a qwen."""

    def test_marker_reasoning_effort_en_error(self):
        """El detector reconoce los mensajes típicos del 400."""
        mensajes_400 = [
            "Error: reasoning_effort is not supported",
            "Unknown parameter: reasoning_effort",
            "extra inputs are not permitted",
            "Unsupported parameter: reasoning_effort",
            "invalid_request_error: reasoning effort rejected",
            "unrecognized argument 'reasoning_effort'",
        ]
        # Smoke: cada uno contiene al menos uno de los keywords del detector
        keywords = (
            "reasoning_effort",
            "reasoning effort",
            "unknown_argument",
            "unknown_parameter",
            "unrecognized",
            "extra inputs are not permitted",
            "unsupported_parameter",
            "unsupported parameter",
            "invalid_request_error",
        )
        for msg in mensajes_400:
            assert any(k in msg.lower() for k in keywords), (
                f"Mensaje '{msg}' no caza con ningún keyword del detector"
            )
