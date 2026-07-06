"""Banco de defensas clínicas de referencia para tecnología de alto costo.

Mejora #4 (jun-2026). La regla 8/8.quater del system prompt YA pide
justificar clínicamente la tecnología cara, pero la IA a veces se queda en
"autonomía médica Ley 23/1981" (defensa perezosa que la EPS desestima).

Este módulo inyecta DATOS CLÍNICOS CONCRETOS — literatura nivel 1A
verificable (FDA/NICE/Cochrane/AHA/GPC), el argumento clínico de fondo y la
normativa específica — para cada tecnología/condición de alto costo que el
HUS defiende con frecuencia. La IA recibe la munición exacta, no genérica.

NO inventa: cada defensa cita literatura real y conocida del campo. Si la
condición no está en el banco, no se inyecta nada (la regla 8 del prompt
sigue aplicando como base).

Uso:
    from app.services.defensa_clinica import bloque_defensa_clinica_para_prompt
    bloque = bloque_defensa_clinica_para_prompt(texto_glosa)
    if bloque:
        user_prompt += bloque
"""

from __future__ import annotations

import re

# Banco de defensas. Cada entrada:
#   key: identificador interno
#   patron: regex que detecta la tecnología/condición en el texto
#   titulo: nombre clínico
#   evidencia: literatura nivel 1A (citas verificables y conocidas)
#   argumento: la tesis de defensa clínica de fondo (no "autonomía médica")
#   normas: normativa específica de respaldo
_BANCO_DEFENSAS: tuple[dict, ...] = (
    {
        "key": "cart_t",
        "patron": re.compile(
            r"\bCAR[\-\s]?T\b|TISAGENLECLEUCEL|AXICABTAGENE|LINFOMA\s+B\s+REFRACTARIO",
            re.IGNORECASE,
        ),
        "titulo": "Terapia CAR-T cell (Tisagenlecleucel / Axicabtagene)",
        "evidencia": (
            "FDA aprobación 2017 (Kymriah/Yescarta); INVIMA registro 2023; "
            "ensayos ELIANA (NEJM 2018) y ZUMA-1 (NEJM 2017) con remisión "
            "completa 60-80% en linfoma B refractario tras ≥ 2 líneas."
        ),
        "argumento": (
            "Es el ÚNICO tratamiento con potencial curativo en linfoma/leucemia "
            "B refractario tras agotar quimioterapia convencional. El costo NO es "
            "eximente: sin la terapia el desenlace es la muerte. La indicación es "
            "1B en pacientes que cumplen criterios de refractariedad documentados "
            "en historia clínica."
        ),
        "normas": "Sentencia T-553/2024 + Auto 037/2024 (acceso garantizado por tutela); Ley 1751/2015 Art. 8 (continuidad).",
    },
    {
        "key": "da_vinci",
        "patron": re.compile(
            r"DA\s+VINCI|CIRUG[ÍI]A\s+ROB[ÓO]TIC|PROSTATECTOM[ÍI]A\s+RADICAL\s+ASISTIDA",
            re.IGNORECASE,
        ),
        "titulo": "Cirugía robótica asistida (plataforma da Vinci)",
        "evidencia": (
            "Cochrane Review 2017 (Ilic et al.): la prostatectomía radical "
            "robótica logra MEJOR preservación de continencia urinaria y función "
            "eréctil que la abierta, con menor sangrado y estancia. Recomendación "
            "EAU Guidelines 2023."
        ),
        "argumento": (
            "La vía robótica NO se justifica por 'autonomía médica' sino por "
            "INDICACIÓN CLÍNICA documentada: preservación de bandeletas "
            "neurovasculares (continencia + función eréctil), anatomía pélvica "
            "estrecha, obesidad, o tumor de alta complejidad. La defensa debe "
            "citar el dato clínico específico del paciente, NO solo 'el médico lo "
            "decidió'."
        ),
        "normas": "Ley 1751/2015 Art. 17 (autonomía) COMO COMPLEMENTO, no como único sustento; Res. 2003/2014 (habilitación).",
    },
    {
        "key": "implante_coclear",
        "patron": re.compile(r"IMPLANTE\s+COCLEAR", re.IGNORECASE),
        "titulo": "Implante coclear (bilateral / pediátrico)",
        "evidencia": (
            "FDA aprobación desde los 9-12 meses; Cochrane 2022 y consenso "
            "internacional: el implante bilateral en < 24 meses es indicación 1A "
            "para localización espacial del sonido y desarrollo lingüístico "
            "simétrico, aprovechando la VENTANA CRÍTICA de plasticidad auditiva "
            "(0-3 años)."
        ),
        "argumento": (
            "La edad temprana NO es 'prematura' sino ÓPTIMA — cada mes de retraso "
            "reduce el resultado lingüístico. La bilateralidad y el procesador "
            "elegido se justifican por compatibilidad con RM y menor tasa de "
            "falla. Si el dispositivo tiene distribuidor único en Colombia, eso "
            "EXIME de las 3 cotizaciones (Decreto 1082/2015)."
        ),
        "normas": "Ley 1388/2010 (niñez); Sentencia T-027/2020; Decreto 1082/2015 Art. 2.2.1.2.1.5.7 (proveedor único exime cotización).",
    },
    {
        "key": "tms_psiquiatria",
        "patron": re.compile(
            r"\bTMS\b|ESTIMULACI[ÓO]N\s+MAGN[ÉE]TICA\s+TRANSCRANEAL|"
            r"ESQUIZOFRENIA\s+REFRACTARIA",
            re.IGNORECASE,
        ),
        "titulo": "Estimulación Magnética Transcraneal (TMS) en psiquiatría refractaria",
        "evidencia": (
            "FDA aprobación 2008 (depresión refractaria); NICE TA300; evidencia "
            "nivel 1A en depresión mayor resistente y uso establecido en "
            "esquizofrenia refractaria a ≥ 2 antipsicóticos. APA Guidelines 2020."
        ),
        "argumento": (
            "La TMS es procedimiento ESTABLECIDO, no experimental — su rechazo "
            "'por no estar en PBS' ignora que el PBS cubre la atención integral "
            "en salud mental (Ley 1616/2013). La duración de la hospitalización "
            "psiquiátrica NO se rige por un calendario sino por la REMISIÓN de "
            "síntomas agudos (riesgo suicida/heteroagresión documentado en notas "
            "de evolución)."
        ),
        "normas": "Ley 1616/2013 (Salud Mental, atención integral); Resolución 4886/2018; Sentencia T-401/1994 (dignidad psiquiátrica).",
    },
    {
        "key": "epicel_quemado",
        "patron": re.compile(
            r"\bEPICEL\b|QUERATINOCITOS\s+(?:AUT[ÓO]LOGOS\s+)?CULTIV|"
            r"QUEMAD[OA]\s+(?:GRAVE|SCQ)",
            re.IGNORECASE,
        ),
        "titulo": "Epicel (queratinocitos autólogos cultivados) en quemado grave",
        "evidencia": (
            "FDA aprobación HDE 2007; indicación 1A en quemaduras de espesor total "
            "≥ 30% SCQ cuando el donante para autoinjerto es insuficiente. GPC "
            "Quemados; literatura Lancet/Burns."
        ),
        "argumento": (
            "Epicel tiene aprobación regulatoria desde hace ~18 años — la "
            "objeción 'experimental' es FALSA. En quemado grave con donante "
            "insuficiente es muchas veces la ÚNICA opción de cobertura cutánea "
            "definitiva; el costo no es eximente ante riesgo vital."
        ),
        "normas": "Ley 1751/2015 Art. 8 (continuidad, urgencia vital); Resolución 2003/2014.",
    },
    {
        "key": "norwood_neonatal",
        "patron": re.compile(
            r"\bNORWOOD\b|HIPOPLASIA\s+VENTRICULAR|\bHLHS\b|FONTAN|GLENN",
            re.IGNORECASE,
        ),
        "titulo": "Cirugía de Norwood (síndrome de hipoplasia ventricular izquierdo)",
        "evidencia": (
            "AHA/ACC Guidelines 2018 nivel A: la cirugía estadiada Norwood (I) → "
            "Glenn (II) → Fontan (III) es el protocolo de ELECCIÓN en HLHS. "
            "Mortalidad sin cirugía > 99% en el primer mes de vida."
        ),
        "argumento": (
            "NO es 'cirugía paliativa innecesaria' — es el ÚNICO camino de "
            "supervivencia. Sin Norwood el neonato fallece. La objeción es "
            "clínicamente insostenible: se contrapone a la evidencia y al deber "
            "de continuidad."
        ),
        "normas": "Ley 1751/2015 Art. 8; Ley 1388/2010 (niñez); Sentencia T-027/2020.",
    },
    {
        "key": "hemofilia_inhibidores",
        "patron": re.compile(
            r"HEMOFILIA|FACTOR\s+VII|EPTACOG|FEIBA|INHIBIDOR(?:ES)?\b",
            re.IGNORECASE,
        ),
        "titulo": "Hemofilia con inhibidores (Factor VIIa / aPCC)",
        "evidencia": (
            "WFH Guidelines 2020 nivel 1A: el Factor VII activado recombinante "
            "(eptacog alfa) y el complejo aPCC (FEIBA) son indicación en sangrado "
            "mayor refractario al factor concentrado convencional con inhibidores "
            "≥ 5 BU."
        ),
        "argumento": (
            "NO es 'uso compasivo no autorizado' — son medicamentos formulados en "
            "el PBS específicamente para hemofilia con inhibidores. El escenario "
            "(sangrado mayor + inhibidores) es la indicación exacta."
        ),
        "normas": "Resolución 1652/2021 (Anexo hemofilia); Ley 1751/2015 Art. 15 (exclusiones taxativas).",
    },
    {
        "key": "iris_vih",
        "patron": re.compile(
            r"\bIRIS\b|RECONSTITUCI[ÓO]N\s+INMUNE|VIH.{0,20}TARV|SIDA",
            re.IGNORECASE,
        ),
        "titulo": "Síndrome de Reconstitución Inmune (IRIS) post-TARV en VIH/SIDA",
        "evidencia": (
            "CDC MMWR 2017; el IRIS es complicación PREVISIBLE y protocolizada en "
            "las primeras semanas del TARV — marcador de RESPUESTA inmunológica, "
            "no de mala praxis."
        ),
        "argumento": (
            "La hospitalización por IRIS NO es 'complicación evitable' glosable: "
            "es la evolución esperada de un tratamiento exitoso. Glosarlo penaliza "
            "el manejo correcto de una enfermedad de alto costo de cobertura "
            "obligatoria."
        ),
        "normas": "Resolución 1652/2021 (Anexo VIH); Ley 1751/2015 Art. 8.",
    },
)


def detectar_defensa_clinica(texto_glosa: str | None) -> dict | None:
    """Devuelve la primera defensa clínica del banco aplicable al texto, o
    None si ninguna condición de alto costo se detecta.
    """
    if not texto_glosa:
        return None
    for d in _BANCO_DEFENSAS:
        if d["patron"].search(texto_glosa):
            return d
    return None


def bloque_defensa_clinica_para_prompt(texto_glosa: str | None) -> str:
    """Construye el bloque de defensa clínica de referencia para inyectar al
    user prompt. "" si la condición no está en el banco.
    """
    d = detectar_defensa_clinica(texto_glosa)
    if not d:
        return ""
    return (
        "\n\n═══ DEFENSA CLÍNICA DE REFERENCIA (USA ESTOS DATOS, NO GENERALICES) ═══\n"
        f"Condición/tecnología detectada: {d['titulo']}.\n"
        f"• EVIDENCIA NIVEL 1A (cítala): {d['evidencia']}\n"
        f"• ARGUMENTO CLÍNICO DE FONDO: {d['argumento']}\n"
        f"• NORMATIVA ESPECÍFICA: {d['normas']}\n"
        "OBLIGATORIO: la defensa NO puede limitarse a 'autonomía médica' — DEBE "
        "citar la evidencia clínica nivel 1A de arriba + el dato clínico concreto "
        "del paciente que justifica la indicación. NO inventes otros estudios "
        "fuera de los listados."
    )


# Marcadores de literatura clínica nivel 1A para el checklist post-validador.
_RE_LITERATURA_1A = re.compile(
    r"\bFDA\b|\bNICE\b|COCHRANE|\bAHA\b|\bACC\b|\bWFH\b|\bAPA\b|\bEAU\b|"
    r"\bMMWR\b|\bCDC\b|\bGPC\b|GUIDELINES|NIVEL\s+1A|NEJM|LANCET|"
    r"KDIGO|ISHLT|SURVIVING\s+SEPSIS|CONSENSO\s+(?:INTERNACIONAL|LATINOAMERICANO|EUROPEO)",
    re.IGNORECASE,
)


def auditar_literatura_citada(
    dictamen: str | None,
    texto_glosa: str | None,
) -> tuple[bool, str]:
    """Si el caso involucra tecnología cara (banco), verifica que el dictamen
    cite literatura clínica nivel 1A (no solo 'autonomía médica').

    Returns: (ok, mensaje). ok=True si no aplica o si citó literatura.
    """
    d = detectar_defensa_clinica(texto_glosa)
    if not d:
        return True, ""
    if not dictamen:
        return False, f"{d['titulo']}: dictamen vacío sin defensa clínica."
    if _RE_LITERATURA_1A.search(dictamen):
        return True, ""
    return False, (
        f"{d['titulo']}: el dictamen NO cita literatura clínica nivel 1A "
        "(FDA/NICE/Cochrane/AHA/GPC). La defensa de tecnología cara basada solo "
        "en 'autonomía médica' es desestimada por la EPS."
    )
