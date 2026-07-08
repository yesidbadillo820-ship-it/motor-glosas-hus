"""Ronda 27 (2-jul-2026) — la degradación silenciosa a Groq y los huecos
que la re-prueba del Caso 1 dejó a la vista.

Reproducción local probó que el router SÍ escaló ($6.4M + 2 PDFs →
Sonnet), pero producción respondió con Groq DOS veces: la llamada a
Anthropic falla y la causa se traga. Fixes:
  1. Etiqueta [degradado de X: causa] — el diagnóstico viaja en el campo
     modelo hasta la UI (y log [MODELO-DEGRADADO]).
  2. Keywords cortas (≤4) con frontera de palabra — "AME" matcheaba
     dentro de "PREVIAMENTE" y escalaba falsos positivos.
  3. Sub-concepto sin refutar → defecto crítico (la prótesis de $3.9M
     quedó muda aunque el detector ya la separaba).
  4. Placeholder dentro de fórmula ("el valor objetado ... - 10% = el
     valor objetado ...") → defecto crítico.
"""

from __future__ import annotations

TEXTO_C1 = (
    "COMPENSAR EPS — GLOSA TA0201 MAYOR VALOR. FACTURA FE-HUS-118432. "
    "CUPS 815103 REEMPLAZO PROTÉSICO TOTAL PRIMARIO SIMPLE DE CADERA. "
    "VALOR FACTURADO: $20.200.092. VALOR OBJETADO: $6.434.900. "
    "OBSERVACIÓN: SE EVIDENCIA MAYOR VALOR COBRADO: LA IPS FACTURA "
    "$7.860.092 CUANDO CORRESPONDE SOAT 2025 MENOS 20% ($5.345.192), SE "
    "GLOSA LA DIFERENCIA DE $2.514.900. ADICIONALMENTE SE GLOSA LA "
    "PRÓTESIS TOTAL DE CADERA POR VALOR DE $3.920.000 POR ENCONTRARSE "
    "INCLUIDA EN EL PAQUETE QUIRÚRGICO."
).upper()


# ─── 1. Etiqueta de degradación anthropic → groq ─────────────────────


async def test_llamar_ia_marca_degradacion_en_la_etiqueta(caplog):
    from app.services.glosa_service import GlosaService

    gs = GlosaService.__new__(GlosaService)
    gs.anthropic_key = "sk-test"
    gs.anthropic_model = "claude-sonnet-4-5"
    gs.groq = object()  # truthy
    gs.primary_ai = "groq"

    async def _anthropic_falla(system, user, modelo_override=None, temperature_override=None):
        raise RuntimeError("HTTP 529: overloaded")

    async def _groq_ok(system, user, llamada_corta=False):
        return "<argumento>OK</argumento>", "groq/llama-4-scout"

    gs._llamar_anthropic = _anthropic_falla
    gs._llamar_groq_con_retry = _groq_ok

    import logging

    with caplog.at_level(logging.WARNING, logger="motor_glosas"):
        content, modelo = await gs._llamar_ia(
            "sys",
            "user",
            modelo_override="claude-sonnet-4-5",
            bypass_cache=True,
        )
    assert content == "<argumento>OK</argumento>"
    # Ronda 29: etiqueta CORTA a BD/UI (la larga desbordaba VARCHAR(80/100)
    # en Postgres); la causa completa viaja al log [MODELO-DEGRADADO].
    assert "[degradado]" in modelo
    assert len(modelo) <= 80
    log_degradado = [r.message for r in caplog.records if "[MODELO-DEGRADADO]" in r.message]
    assert log_degradado and "529" in log_degradado[0]
    assert "claude-sonnet-4-5" in log_degradado[0]


async def test_llamar_ia_sin_override_no_agrega_etiqueta():
    from app.services.glosa_service import GlosaService

    gs = GlosaService.__new__(GlosaService)
    gs.anthropic_key = ""
    gs.anthropic_model = "claude-sonnet-4-5"
    gs.groq = object()
    gs.primary_ai = "groq"

    async def _groq_ok(system, user, llamada_corta=False):
        return "<argumento>OK</argumento>", "groq/llama-4-scout"

    gs._llamar_groq_con_retry = _groq_ok

    _, modelo = await gs._llamar_ia("sys", "user", bypass_cache=True)
    assert "degradado" not in modelo


# ─── 2. Keywords cortas con frontera de palabra ──────────────────────


def test_ame_no_matchea_dentro_de_adverbios():
    from app.services.routing_complejidad import detectar_complejidad_critica

    res = detectar_complejidad_critica(
        valor=100_000,
        num_pdfs=0,
        num_codigos=1,
        texto_glosa="EL PACIENTE FUE VALORADO PREVIAMENTE Y ADECUADAMENTE POR ORTOPEDIA",
        contexto_pdf="",
    )
    assert not any("AME" in m for m in res.motivos), res.motivos


def test_ame_como_palabra_si_escala():
    from app.services.routing_complejidad import detectar_complejidad_critica

    res = detectar_complejidad_critica(
        valor=100_000,
        num_pdfs=0,
        num_codigos=1,
        texto_glosa="PACIENTE CON AME TIPO 1 EN SEGUIMIENTO POR NEUROPEDIATRIA",
        contexto_pdf="",
    )
    assert res.es_complejo and any("AME" in m for m in res.motivos)


# ─── 3. Sub-concepto sin refutar → defecto crítico ───────────────────

_ARG_SOLO_TARIFA = (
    "<paciente>X</paciente><servicio>Y</servicio>"
    "<argumento>ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE MAYOR VALOR. LA "
    "TARIFA APLICABLE ES SOAT MENOS DIEZ POR CIENTO SEGÚN EL ACUERDO "
    "TARIFARIO 2025 Y EL VALOR FACTURADO CORRESPONDE A LO PACTADO. SE "
    "SOLICITA EL LEVANTAMIENTO INTEGRAL.</argumento>"
)


def test_subconcepto_protesis_sin_respuesta_es_defecto():
    from app.services.validador_dictamen import detectar_defectos_criticos

    defectos = detectar_defectos_criticos(
        _ARG_SOLO_TARIFA, codigo_glosa="TA0201", texto_glosa=TEXTO_C1
    )
    assert any(d["regla"] == "subconcepto_sin_respuesta" for d in defectos)


def test_subconcepto_respondido_no_es_defecto():
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>X</paciente><servicio>Y</servicio>"
        "<argumento>ESE HUS NO ACEPTA LA GLOSA. PRIMERO, LA TARIFA ES SOAT "
        "MENOS DIEZ SEGÚN EL ACUERDO TARIFARIO 2025. SEGUNDO, LA PRÓTESIS "
        "NO SE ENCUENTRA INCLUIDA EN EL PAQUETE QUIRÚRGICO: SU SUMINISTRO "
        "SE FACTURA POR SEPARADO CONFORME AL ANEXO TARIFARIO. SE SOLICITA "
        "EL LEVANTAMIENTO.</argumento>"
    )
    defectos = detectar_defectos_criticos(xml, codigo_glosa="TA0201", texto_glosa=TEXTO_C1)
    assert not any(d["regla"] == "subconcepto_sin_respuesta" for d in defectos)


def test_glosa_de_un_solo_concepto_no_dispara_subconcepto():
    from app.services.validador_dictamen import detectar_defectos_criticos

    defectos = detectar_defectos_criticos(
        _ARG_SOLO_TARIFA,
        codigo_glosa="TA0201",
        texto_glosa="SE GLOSA MAYOR VALOR EN LA FACTURA POR DIFERENCIA TARIFARIA SOAT.",
    )
    assert not any(d["regla"] == "subconcepto_sin_respuesta" for d in defectos)


# ─── 4. Placeholder dentro de fórmula ────────────────────────────────


def test_placeholder_en_formula_es_defecto():
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>X</paciente><servicio>Y</servicio>"
        "<argumento>LA TARIFA APLICABLE CORRESPONDE A SOAT 2025 MENOS 10% "
        "(EL VALOR OBJETADO CONSIGNADO EN EL EXPEDIENTE - 10% = EL VALOR "
        "OBJETADO CONSIGNADO EN EL EXPEDIENTE). SE SOLICITA EL "
        "LEVANTAMIENTO.</argumento>"
    )
    defectos = detectar_defectos_criticos(xml, codigo_glosa="TA0201")
    assert any(d["regla"] == "placeholder_en_formula" for d in defectos)


def test_placeholder_en_prosa_normal_no_es_defecto():
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>X</paciente><servicio>Y</servicio>"
        "<argumento>ESE HUS NO ACEPTA LA GLOSA POR EL VALOR OBJETADO "
        "CONSIGNADO EN EL EXPEDIENTE, DADO QUE LA TARIFA APLICADA ES LA "
        "PACTADA. SE SOLICITA EL LEVANTAMIENTO.</argumento>"
    )
    defectos = detectar_defectos_criticos(xml, codigo_glosa="TA0201")
    assert not any(d["regla"] == "placeholder_en_formula" for d in defectos)
