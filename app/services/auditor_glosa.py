"""Auditor pre-IA de glosas (R-cerebro #9).

Antes de gastar tokens del LLM, este módulo HACE auditoría real:
compara lo que la EPS afirma en el texto de la glosa contra los
datos verificados del sistema (contrato cargado, tarifa pactada,
CUPS en catálogo, etc.) y detecta INCONSISTENCIAS — afirmaciones
de la EPS que el sistema puede demostrar falsas.

Resultado: lista de hallazgos con severidad. La IA recibe esa lista
en el user_prompt y DEBE refutar cada hallazgo punto por punto. Si
los hallazgos son contundentes y unívocos, el motor puede emitir
respuesta directamente con texto fijo (ahorro total de tokens).

Filosofía:
  • TODO determinístico — regex + lookup en BD. Cero LLM.
  • Compara afirmaciones EPS vs datos verificados.
  • Severidad ALTA = mentira demostrable; MEDIA = ambigüedad;
    BAJA = matiz menor.
  • Output: dict con `hallazgos`, `score_evidencia`, `accion_sugerida`.
"""
from __future__ import annotations

import re
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# Patrones de afirmaciones típicas de las EPS
# ──────────────────────────────────────────────────────────────────────

# La EPS dice que no hay contrato (cuando puede haberlo)
_PAT_SIN_CONTRATO = re.compile(
    r"(?:SIN\s+CONTRATO|NO\s+(?:EXISTE|HAY)\s+CONTRATO|"
    r"AUSENCIA\s+DE\s+CONTRATO|NO\s+TIENE\s+CONTRATO|"
    r"NO\s+SE\s+EVIDENCIA\s+CONTRATO|NO\s+SE\s+EVIDENCIA\s+ACUERDO)",
    re.IGNORECASE,
)

# La EPS dice que no hay tarifa pactada (cuando sí está en el catálogo)
_PAT_SIN_TARIFA_PACTADA = re.compile(
    r"(?:NO\s+(?:HAY|EXISTE|SE\s+EVIDENCIA|TIENE)\s+TARIFA\s+PACTAD[AO]|"
    r"AUSENCIA\s+DE\s+TARIFA|"
    r"SIN\s+TARIFA\s+PACTAD[AO]|"
    r"NO\s+HAY\s+(?:VALOR|TARIFA)\s+(?:PACTAD[AO]|CONVENID[AO]|ACORDAD[AO]))",
    re.IGNORECASE,
)

# La EPS aplica SOAT como sustituto del contrato
_PAT_APLICA_SOAT = re.compile(
    r"(?:SE\s+RECONOCE\s+(?:A\s+)?(?:TARIFA\s+)?SOAT|"
    r"APLICA\s+(?:TARIFA\s+)?SOAT|"
    r"SE\s+PAGA\s+(?:A\s+)?(?:TARIFA\s+)?SOAT|"
    r"TARIFA\s+SOAT\s+VIGENTE)",
    re.IGNORECASE,
)

# La EPS dice que no hay autorización
_PAT_SIN_AUTORIZACION = re.compile(
    r"(?:SIN\s+AUTORIZACI[ÓO]N|NO\s+(?:HAY|EXISTE|SE\s+EVIDENCIA)\s+"
    r"AUTORIZACI[ÓO]N|FALTA\s+AUTORIZACI[ÓO]N)",
    re.IGNORECASE,
)

# La EPS dice que falta historia clínica
_PAT_SIN_HISTORIA = re.compile(
    r"(?:SIN\s+HISTORIA\s+CL[IÍ]NICA|NO\s+(?:HAY|SE\s+(?:ANEX[ÓO]|APORT[ÓO]))\s+HISTORIA|"
    r"FALTA\s+HISTORIA\s+CL[IÍ]NICA)",
    re.IGNORECASE,
)

# La EPS dice "se glosa la diferencia" (modus operandi: reconoce parte)
_PAT_GLOSA_DIFERENCIA = re.compile(
    r"(?:SE\s+GLOSA\s+LA\s+DIFERENCIA|GLOSA\s+POR\s+DIFERENCIA|"
    r"OBJETA\s+(?:LA\s+)?DIFERENCIA)",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────
# Auditor principal
# ──────────────────────────────────────────────────────────────────────

def auditar(
    texto_glosa: str,
    *,
    eps: Optional[str] = None,
    codigo: Optional[str] = None,
    cups: Optional[str] = None,
    tiene_contrato: bool = False,
    valor_facturado: float = 0.0,
    valor_pactado: float = 0.0,
    valor_objetado: float = 0.0,
    contexto_pdf: str = "",
) -> dict:
    """Audita las afirmaciones de la EPS contra los datos del sistema.

    Retorna:
      {
        "hallazgos": [{"id", "severidad", "afirmacion_eps",
                       "realidad_sistema", "refutacion_sugerida"}],
        "score_evidencia": 0..100,  # qué tan contundente es la defensa
        "accion_sugerida": str,
        "puede_responder_solo": bool,   # si True, no hace falta LLM
      }
    """
    texto = (texto_glosa or "").strip()
    pdf = (contexto_pdf or "").strip()
    hallazgos: list[dict] = []

    # ── HALLAZGO 1: La EPS afirma "sin contrato" pero el sistema
    #    tiene contrato vigente.
    if _PAT_SIN_CONTRATO.search(texto) and tiene_contrato:
        hallazgos.append({
            "id": "afirmacion_sin_contrato_falsa",
            "severidad": "ALTA",
            "afirmacion_eps": (
                "La EPS afirma que NO existe contrato entre las partes."
            ),
            "realidad_sistema": (
                "El sistema tiene cargado un contrato vigente para esta "
                "entidad pagadora, con tarifa pactada en el catálogo "
                "institucional."
            ),
            "refutacion_sugerida": (
                "Refutar PUNTUALMENTE que la afirmación NO se ajusta a "
                "la realidad documental: el contrato existe, está "
                "vigente y la tarifa pactada está incorporada al "
                "acuerdo. Citar número de contrato + Art. 1602 C.C. "
                "(contrato es ley entre partes)."
            ),
        })

    # ── HALLAZGO 2: La EPS afirma "sin tarifa pactada" pero el sistema
    #    sí tiene la tarifa cargada.
    if _PAT_SIN_TARIFA_PACTADA.search(texto) and valor_pactado > 0:
        hallazgos.append({
            "id": "afirmacion_sin_tarifa_falsa",
            "severidad": "ALTA",
            "afirmacion_eps": (
                "La EPS afirma que no hay tarifa pactada para el "
                "servicio facturado."
            ),
            "realidad_sistema": (
                f"El sistema tiene cargada una tarifa pactada de "
                f"${valor_pactado:,.0f} para el CUPS {cups or ''} en el "
                "tarifario institucional incorporado al contrato."
            ),
            "refutacion_sugerida": (
                "Citar el monto exacto pactado y la fuente (tarifario "
                "del contrato). El argumento de \"sin tarifa\" es "
                "objetivamente desmentible."
            ),
        })

    # ── HALLAZGO 3: La EPS aplica SOAT como sustituto cuando hay
    #    contrato con tarifa propia. SOAT es supletorio, no aplicable
    #    cuando hay pacto contractual específico.
    if _PAT_APLICA_SOAT.search(texto) and tiene_contrato and valor_pactado > 0:
        hallazgos.append({
            "id": "soat_sustituto_indebido",
            "severidad": "ALTA",
            "afirmacion_eps": (
                "La EPS aplica tarifa SOAT (vigente o histórica) como "
                "criterio liquidatorio."
            ),
            "realidad_sistema": (
                "Existe contrato vigente con tarifa propia pactada. "
                "El SOAT solo aplica cuando NO hay contrato; cuando "
                "el contrato pactó otra tarifa, esa rige por "
                "especialidad sobre la regla supletiva."
            ),
            "refutacion_sugerida": (
                "Sostener que la sustitución unilateral de la tarifa "
                "pactada por SOAT carece de respaldo contractual y "
                "viola Art. 871 C.Comercio (buena fe en ejecución)."
            ),
        })

    # ── HALLAZGO 4: Coherencia numérica. Si la EPS objeta más que el
    #    excedente real (facturado − pactado), está reduciendo la
    #    base contractual y eso es indefendible para ella.
    if (
        valor_facturado > 0 and valor_pactado > 0
        and valor_objetado > 0 and valor_facturado >= valor_pactado
    ):
        excedente = valor_facturado - valor_pactado
        if valor_objetado > excedente + 1:
            # La EPS está objetando MÁS que lo que está fuera del
            # contrato — afecta la base pactada.
            hallazgos.append({
                "id": "objeta_mas_que_excedente",
                "severidad": "ALTA",
                "afirmacion_eps": (
                    f"La EPS objeta ${valor_objetado:,.0f} cuando el "
                    f"excedente sobre lo pactado es solo "
                    f"${excedente:,.0f}."
                ),
                "realidad_sistema": (
                    f"La diferencia entre lo objetado y el excedente "
                    f"real es ${valor_objetado - excedente:,.0f}. Ese "
                    "monto sí está cubierto por la tarifa pactada — "
                    "objetarlo es desconocer el contrato."
                ),
                "refutacion_sugerida": (
                    f"Aceptar parcialmente ${excedente:,.0f} (el "
                    f"excedente real); defender los ${valor_objetado - excedente:,.0f} "
                    "restantes como pactados."
                ),
            })

    # ── HALLAZGO 5: Glosa "la diferencia" sin señalar cifra concreta
    #    ni indicar contra qué tarifa de referencia.
    if _PAT_GLOSA_DIFERENCIA.search(texto):
        hallazgos.append({
            "id": "diferencia_sin_referente",
            "severidad": "MEDIA",
            "afirmacion_eps": (
                "La EPS glosa \"la diferencia\" sin precisar el "
                "referente tarifario aplicado."
            ),
            "realidad_sistema": (
                "Una glosa válida debe identificar (a) el valor "
                "pactado contractual y (b) la diferencia exacta. "
                "Glosar abstractamente no acredita el motivo."
            ),
            "refutacion_sugerida": (
                "Pedir que la EPS especifique el referente normativo "
                "y la diferencia exacta — invocar Resolución 2284/2023 "
                "que exige motivación detallada en la objeción."
            ),
        })

    # ── HALLAZGO 6: Falta de historia clínica afirmada por EPS pero
    #    el expediente sí adjunta PDFs.
    if _PAT_SIN_HISTORIA.search(texto) and pdf and len(pdf) > 500:
        hallazgos.append({
            "id": "historia_aportada_objetada",
            "severidad": "MEDIA",
            "afirmacion_eps": (
                "La EPS afirma que falta la historia clínica."
            ),
            "realidad_sistema": (
                f"El expediente aporta {len(pdf):,} caracteres "
                "extraídos del PDF — historia clínica/RIPS/factura "
                "presentes en autos."
            ),
            "refutacion_sugerida": (
                "Citar Resolución 1995/1999: la historia clínica es "
                "documento médico-legal de plena prueba y obra en "
                "autos. La afirmación de \"falta\" no se ajusta a la "
                "realidad documental."
            ),
        })

    # ── Score de evidencia: 100 = caso unívoco a favor del prestador.
    severidad_pesos = {"ALTA": 30, "MEDIA": 15, "BAJA": 5}
    score = min(
        100,
        sum(severidad_pesos.get(h["severidad"], 0) for h in hallazgos),
    )

    # ── Acción sugerida y posibilidad de responder sin LLM.
    accion = "REVISAR"
    puede_solo = False
    if score >= 60:
        accion = "DEFENDER_FUERTE"
    elif score >= 30:
        accion = "DEFENDER"

    return {
        "hallazgos": hallazgos,
        "score_evidencia": score,
        "accion_sugerida": accion,
        "puede_responder_solo": puede_solo,
        "n_hallazgos_alta": sum(
            1 for h in hallazgos if h["severidad"] == "ALTA"
        ),
    }


def bloque_auditoria_para_prompt(auditoria: dict) -> str:
    """Formatea la auditoría como bloque para el user_prompt."""
    if not auditoria or not auditoria.get("hallazgos"):
        return ""
    partes = [
        "",
        "═══ 🔍 AUDITORÍA PREVIA — INCONSISTENCIAS DETECTADAS POR EL SISTEMA ═══",
        (
            f"Score de evidencia a favor del prestador: "
            f"{auditoria.get('score_evidencia', 0)}/100. "
            f"Acción sugerida: {auditoria.get('accion_sugerida', 'REVISAR')}."
        ),
        "",
        "El sistema YA comparó las afirmaciones de la EPS contra los",
        "datos verificados. Tu dictamen DEBE refutar UNO POR UNO los",
        "siguientes hallazgos en el párrafo 2 (REFUTACIÓN FÁCTICA),",
        "citando expresamente que \"la afirmación de la EPS no se",
        "ajusta a la realidad documental\":",
        "",
    ]
    for i, h in enumerate(auditoria["hallazgos"], 1):
        sev = h.get("severidad", "MEDIA")
        marker = "🔴" if sev == "ALTA" else ("🟡" if sev == "MEDIA" else "🟢")
        partes.append(f"  {i}. {marker} [{sev}] {h['afirmacion_eps']}")
        partes.append(f"     ↳ Realidad: {h['realidad_sistema']}")
        partes.append(f"     ↳ Cómo refutar: {h['refutacion_sugerida']}")
        partes.append("")
    partes.append(
        "⚠ NO redactes argumentos genéricos sobre \"buena fe contractual\""
    )
    partes.append(
        "  sin antes ATACAR PUNTUALMENTE los hallazgos de arriba. Esa es la"
    )
    partes.append(
        "  diferencia entre un dictamen de plantilla y uno con auditoría real."
    )
    partes.append("═══════════════════════════════════════════════════════════")
    partes.append("")
    return "\n".join(partes)


def construir_bloque_auditoria(
    texto_glosa: str,
    *,
    eps: Optional[str] = None,
    codigo: Optional[str] = None,
    cups: Optional[str] = None,
    tiene_contrato: bool = False,
    valor_facturado: float = 0.0,
    valor_pactado: float = 0.0,
    valor_objetado: float = 0.0,
    contexto_pdf: str = "",
) -> str:
    """Helper de un solo paso: audita y formatea."""
    try:
        a = auditar(
            texto_glosa,
            eps=eps, codigo=codigo, cups=cups,
            tiene_contrato=tiene_contrato,
            valor_facturado=valor_facturado,
            valor_pactado=valor_pactado,
            valor_objetado=valor_objetado,
            contexto_pdf=contexto_pdf,
        )
        return bloque_auditoria_para_prompt(a)
    except Exception:
        return ""
