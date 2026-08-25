"""Analizador del motivo de la EPS (R-cerebro mejora #6).

Antes de redactar el dictamen, extraemos del TEXTO DE LA GLOSA los
puntos concretos que la EPS está objetando, para que el LLM los
ataque uno por uno en el párrafo 2 (refutación fáctica).

Heurísticas (regex), nada de IA aquí — es pre-procesamiento barato
y determinístico. El bloque resultante se anexa al user_prompt.

Detecta:
  - motivo_principal: la frase clave del argumento de la EPS
  - valor_reconocido: $X que la EPS dice que sí paga
  - descuento_aplicado: descuento unilateral (-X%, UVB sustituto, etc.)
  - soportes_faltantes: documentos que la EPS dice que faltan
  - cups_alternativo: CUPS que la EPS PROPONE como sustituto
  - exige_devolucion: si pide reversar/devolver
  - normas_citadas_eps: leyes/decretos que cita la EPS
"""

from __future__ import annotations

import re

# ──────────────────────────────────────────────────────────────────────
# Patrones reutilizables
# ──────────────────────────────────────────────────────────────────────

# Valor reconocido por la EPS
_PAT_RECONOCE = re.compile(
    r"(?:SE\s+RECONOCE|RECONOCEMOS|SE\s+PAGA|RECONOCIDO)[^$]{0,40}?"
    r"\$\s*([\d.,]+)",
    re.IGNORECASE,
)

# Descuento unilateral
_PAT_DESCUENTO = re.compile(
    r"(SOAT\s*-?\s*\d{1,2}\s*%|"
    r"-\s*\d{1,2}\s*%|"
    r"DESCUENTO\s+DEL?\s+\d{1,2}\s*%|"
    r"TARIFA\s+UVB|"
    r"UVB\s+VIGENTE|"
    r"FACTOR\s+\d+\.\d+)",
    re.IGNORECASE,
)

# CUPS alternativo propuesto por la EPS (vs el facturado)
_PAT_CUPS_ALT = re.compile(
    r"(?:SE\s+RECONOCE|TARIFA\s+SOAT)[^.]{0,80}?"
    r"(?:C[ÓO]DIGO|CUPS)\s+(\d{4,7}[A-Z]?\d*)",
    re.IGNORECASE,
)

# Soportes que la EPS dice que faltan
_PAT_SOPORTES_FALT = re.compile(
    r"(?:FALTA|NO\s+(?:SE\s+)?(?:ANEX[OAÓ]|APORT[AÓO]|REMITI[ÓO])|"
    r"SIN|AUSENCIA\s+DE)\s+"
    r"(HISTORIA\s+CL[ÍI]NICA|EPICRISIS|RIPS|"
    r"AUTORIZACI[ÓO]N|ORDEN\s+M[ÉE]DICA|"
    r"F[ÓO]RMULA(?:\s+M[ÉE]DICA)?|"
    r"REPORTE\s+(?:DE\s+)?(?:LABORATORIO|RADIOLOG[ÍI]A|PATOLOG[ÍI]A)|"
    r"NOTA\s+M[ÉE]DICA|EVOLUCI[ÓO]N|"
    r"REGISTRO\s+(?:DE\s+)?(?:PROCEDIMIENTO|CIRUG[ÍI]A)|"
    r"FIRMA\s+M[ÉE]DICA|"
    r"SOPORTE[S]?(?:\s+\w+)?|"
    r"DOCUMENTO[S]?(?:\s+\w+)?)",
    re.IGNORECASE,
)

# Pedido de devolución/reverso
_PAT_DEVOLUCION = re.compile(
    r"(?:DEVOLUCI[ÓO]N|REVERS[AO]R?|RECUPERAR|REINTEGRO|"
    r"DEVOLVER\s+EL?\s+VALOR)",
    re.IGNORECASE,
)

# Normas citadas por la EPS
# Ronda 21 (caso MEDIMÁS): ampliado para capturar abreviaturas (Res., Dto.,
# Dec.), año con slash (Decreto 4747/2007) y sufijo de artículo contiguo
# (Art. 20). Antes "Res. 0112/2012" y "Decreto 4747/2007 Art. 20" no se
# extraían y nunca llegaban al bloque de puntos a refutar del prompt.
_PAT_NORMA = re.compile(
    r"\b(LEY\s+\d+(?:\s*(?:DE|/)\s*\d{4})?(?:\s+ART\.?\s*\d+)?|"
    r"(?:RESOLUCI[ÓO]N|RES\.)\s+\d+(?:\s*[/\s]\s*\d{4})?(?:\s+ART\.?\s*\d+)?|"
    r"(?:DECRETO|DTO\.|DEC\.)\s+\d+(?:\s*(?:DE|/)\s*\d{4})?(?:\s+ART\.?\s*\d+)?|"
    r"CIRCULAR\s+\d+(?:[/\s]\d{4})?)",
    re.IGNORECASE,
)

# Frases de pertinencia (criterio médico cuestionado)
_PAT_PERTINENCIA = re.compile(
    r"(NO\s+(?:ES\s+)?PERTINENTE|FALTA\s+JUSTIFICACI[ÓO]N\s+CL[ÍI]NICA|"
    r"NO\s+SE\s+JUSTIFICA|CRITERIO\s+M[ÉE]DICO|"
    r"AUDITOR[ÍI]A\s+CL[ÍI]NICA|REVISI[ÓO]N\s+CL[ÍI]NICA)",
    re.IGNORECASE,
)


# ── Dos causales que se le escapaban (24-08-2026) ─────────────────────
#
# La auditoría encontró tres dictámenes que contestaron algo distinto de lo
# que la EPS levantó:
#
#   · GL-194 y GL-202 — la EPS glosó «precio superior al regulado» de un
#     medicamento (Abiraterona) y el dictamen respondió sobre la validez
#     formal de la factura electrónica y sobre la tarifa SOAT del contrato,
#     sin tocar la regulación de precios ni una vez.
#   · GL-190 — la EPS pidió «se reliquida a manual ISS 2001» y el dictamen
#     nunca dice por qué el ISS 2001 no aplica: solo reafirma que rige SOAT.
#
# Ninguna de las dos causales tenía patrón, así que el bloque que le dice al
# motor qué atacar salía vacío y la respuesta se iba por lo genérico.
_PAT_PRECIO_REGULADO = re.compile(
    r"(PRECIO\s+(?:SUPERIOR|POR\s+ENCIMA)\s+(?:AL?\s+)?(?:PRECIO\s+)?REGULADO|"
    r"PRECIO\s+M[ÁA]XIMO\s+DE\s+VENTA|CONTROL\s+DIRECTO\s+DE\s+PRECIOS|"
    r"MEDICAMENTO\s+REGULADO|CNPMDM|CIRCULAR\s+19\s+DE\s+2024|"
    r"SOBRECOSTO\s+(?:DE|EN)\s+MEDICAMENTO)",
    re.IGNORECASE,
)
_PAT_MANUAL_ALTERNO = re.compile(
    r"(RELIQUID\w*\s+(?:A|SEG[ÚU]N|CON)\s+(?:EL\s+)?MANUAL|"
    r"MANUAL\s+ISS\s*2001|\bISS\s*2001\b|"
    r"SE\s+LIQUIDA\s+(?:A|SEG[ÚU]N)\s+(?:EL\s+)?MANUAL)",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────


def extraer_puntos_eps(texto_glosa: str) -> dict:
    """Extrae los puntos clave del motivo de la EPS.

    Retorna dict con campos siempre presentes (None / [] si no aplica):
      motivo_principal, valor_reconocido, descuento_aplicado,
      cups_alternativo, soportes_faltantes, exige_devolucion,
      normas_citadas_eps, cuestiona_pertinencia
    """
    texto = (texto_glosa or "").strip()
    if not texto:
        return _vacio()

    # Tomamos las primeras 800 chars como "motivo principal"
    motivo_principal = re.sub(r"\s+", " ", texto[:800]).strip() if texto else None

    # Valor reconocido
    valor_reconocido = None
    m = _PAT_RECONOCE.search(texto)
    if m:
        valor_reconocido = "$" + m.group(1).strip().rstrip(".,")

    # Descuento aplicado
    descuento_aplicado = None
    m = _PAT_DESCUENTO.search(texto)
    if m:
        descuento_aplicado = m.group(1).strip().upper()

    # CUPS alternativo
    cups_alternativo = None
    m = _PAT_CUPS_ALT.search(texto)
    if m:
        cups_alternativo = m.group(1).strip()

    # Soportes faltantes (todos los matches)
    soportes_faltantes = []
    for m in _PAT_SOPORTES_FALT.finditer(texto):
        item = m.group(1).strip().upper()
        # Normaliza espacios múltiples
        item = re.sub(r"\s+", " ", item)
        if item not in soportes_faltantes:
            soportes_faltantes.append(item)
        if len(soportes_faltantes) >= 6:
            break

    # Exige devolución
    exige_devolucion = bool(_PAT_DEVOLUCION.search(texto))

    # Normas citadas por la EPS
    normas_citadas_eps = []
    for m in _PAT_NORMA.finditer(texto):
        norma = re.sub(r"\s+", " ", m.group(1).strip()).upper()
        if norma not in normas_citadas_eps:
            normas_citadas_eps.append(norma)
        if len(normas_citadas_eps) >= 5:
            break

    # Pertinencia clínica
    cuestiona_pertinencia = bool(_PAT_PERTINENCIA.search(texto))

    return {
        "precio_regulado": bool(_PAT_PRECIO_REGULADO.search(texto)),
        "manual_alterno": (
            _PAT_MANUAL_ALTERNO.search(texto).group(1).strip().upper()
            if _PAT_MANUAL_ALTERNO.search(texto)
            else None
        ),
        "motivo_principal": motivo_principal,
        "valor_reconocido": valor_reconocido,
        "descuento_aplicado": descuento_aplicado,
        "cups_alternativo": cups_alternativo,
        "soportes_faltantes": soportes_faltantes,
        "exige_devolucion": exige_devolucion,
        "normas_citadas_eps": normas_citadas_eps,
        "cuestiona_pertinencia": cuestiona_pertinencia,
    }


def _vacio() -> dict:
    return {
        "precio_regulado": False,
        "manual_alterno": None,
        "motivo_principal": None,
        "valor_reconocido": None,
        "descuento_aplicado": None,
        "cups_alternativo": None,
        "soportes_faltantes": [],
        "exige_devolucion": False,
        "normas_citadas_eps": [],
        "cuestiona_pertinencia": False,
    }


def bloque_puntos_a_refutar(puntos: dict) -> str:
    """Construye el bloque a anexar al user_prompt para que el LLM
    sepa qué debe atacar punto por punto.

    Solo emite el bloque si hay AL MENOS UN punto detectado.
    """
    if not puntos:
        return ""
    tiene_algo = any(
        [
            puntos.get("valor_reconocido"),
            puntos.get("descuento_aplicado"),
            puntos.get("cups_alternativo"),
            puntos.get("soportes_faltantes"),
            puntos.get("exige_devolucion"),
            puntos.get("cuestiona_pertinencia"),
            puntos.get("precio_regulado"),
            puntos.get("manual_alterno"),
        ]
    )
    if not tiene_algo:
        # SIN PUNTOS RECONOCIDOS, IGUAL SE LE PONE LA CAUSAL DELANTE
        # (24-08-2026). Antes, si ninguno de los patrones enganchaba, este
        # bloque desaparecía entero y el motor se quedaba sin nadie que le
        # dijera QUÉ tenía que refutar. Ahí es donde se colaban los dictámenes
        # que contestan otra cosa: la EPS glosaba «precio superior al
        # regulado» y la respuesta hablaba de la validez formal de la factura.
        # Los patrones no pueden cubrir todas las formas de escribir una
        # objeción, pero el texto literal de la EPS siempre está: se le pone
        # delante y se le exige contestar ESO.
        motivo = (puntos.get("motivo_principal") or "").strip()
        if not motivo:
            return ""
        return "\n".join(
            [
                "",
                "═══ LO QUE LA EPS OBJETA (texto literal de la glosa) ═══",
                f"  «{motivo[:400]}»",
                "",
                "Tu párrafo 2 DEBE contestar ESA afirmación, no otra. Si respondes",
                "sobre un tema distinto —aunque sea correcto— la EPS ratifica la",
                "glosa: lo que no se contesta se da por aceptado.",
                "",
            ]
        )

    partes = [
        "",
        "═══ PUNTOS DE LA EPS A REFUTAR (auto-extraídos del texto de la glosa) ═══",
        "Tu párrafo 2 DEBE atacar UNO POR UNO los siguientes puntos:",
        "",
    ]
    n = 1
    if puntos.get("valor_reconocido"):
        partes.append(
            f"  {n}. La EPS reconoce solo {puntos['valor_reconocido']} — "
            "argumenta que la liquidación correcta corresponde al "
            "VALOR FACTURADO según el contrato/manual aplicable."
        )
        n += 1
    if puntos.get("descuento_aplicado"):
        partes.append(
            f"  {n}. La EPS aplica un descuento unilateral "
            f'("{puntos["descuento_aplicado"]}") — invoca Art. 871 '
            "C.Comercio (buena fe) y Art. 1602 C.Civil (contrato es ley "
            "entre partes) para sostener que NO es admisible modificar "
            "tarifa pactada en vía de glosa."
        )
        n += 1
    if puntos.get("cups_alternativo"):
        partes.append(
            f"  {n}. La EPS propone CUPS alternativo "
            f"({puntos['cups_alternativo']}) — sostén que el CUPS "
            "facturado por HUS es el que CORRESPONDE al servicio "
            "prestado y consta en historia clínica; el alternativo "
            "no refleja la complejidad real."
        )
        n += 1
    if puntos.get("soportes_faltantes"):
        soportes = ", ".join(puntos["soportes_faltantes"][:3])
        partes.append(
            f"  {n}. La EPS dice que faltan: {soportes} — refuta con "
            "Resolución 1995/1999 (historia clínica como plena prueba "
            "médico-legal), la norma de RIPS vigente al momento de la "
            "prestación (Res. 948/2026; Res. 2275/2023 si el servicio "
            "es anterior al 14-05-2026), y Circular "
            "030/2013 si son errores formales subsanables."
        )
        n += 1
    if puntos.get("cuestiona_pertinencia"):
        partes.append(
            f"  {n}. La EPS cuestiona pertinencia clínica — invoca "
            "Art. 17 Ley 1751/2015 (autonomía médica). "
            "Recalca que el médico tratante es el competente para "
            "valorar; auditoría administrativa NO sustituye criterio "
            "clínico."
        )
        n += 1
    if puntos.get("precio_regulado"):
        partes.append(
            f"  {n}. La EPS dice que el precio supera el REGULADO — este es el "
            "punto a atacar, no la validez de la factura ni la tarifa del "
            "contrato. Responde sobre la regulación de precios: la Circular 19 "
            "de 2024 del CNPMDM fija el precio máximo por MERCADO RELEVANTE "
            "(mg/unidad), y su Parágrafo 2 del Art. 1 permite a la IPS "
            "ADICIONAR el margen del Art. 11 de la Circular 18 de 2024. Exige "
            "que la EPS indique el CUM, el mercado relevante y el precio máximo "
            "concreto con que hizo la comparación."
        )
        n += 1
    if puntos.get("manual_alterno"):
        partes.append(
            f"  {n}. La EPS pide reliquidar con otro manual "
            f'("{puntos["manual_alterno"]}") — NO basta con reafirmar cuál rige. '
            "Di EXPRESAMENTE por qué ese manual NO aplica a este contrato y a "
            "este servicio: qué manual quedó pactado, en qué cláusula, y desde "
            "cuándo. Sin esa explicación la EPS ratifica."
        )
        n += 1
    if puntos.get("exige_devolucion"):
        partes.append(
            f"  {n}. La EPS exige devolución/recuperación — sostén que "
            "el servicio fue efectivamente prestado y documentado "
            "(Art. 177 Ley 100/1993 obliga al pago)."
        )
        n += 1

    if puntos.get("normas_citadas_eps"):
        partes.append("")
        partes.append(
            "Normas que cita la EPS (puedes contrastarlas o aceptarlas "
            "según convenga): " + ", ".join(puntos["normas_citadas_eps"])
        )

    partes.append("")
    partes.append(
        "⚠ Si dejas algún punto SIN refutar, la EPS lo usará para "
        "ratificar. Cada punto = una razón enumerada en P2 "
        "(EN PRIMER LUGAR / EN SEGUNDO LUGAR / EN TERCER LUGAR)."
    )
    partes.append("═══════════════════════════════════════════════════════════")
    partes.append("")
    return "\n".join(partes)


def construir_bloque_motivo_eps(texto_glosa: str) -> str:
    """Helper de un solo paso: parsea y formatea."""
    try:
        puntos = extraer_puntos_eps(texto_glosa)
        return bloque_puntos_a_refutar(puntos)
    except Exception:
        return ""
