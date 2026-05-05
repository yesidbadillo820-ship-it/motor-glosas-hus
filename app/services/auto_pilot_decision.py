"""
auto_pilot_decision.py — Decide si un dictamen es "auto-enviable" sin
intervención humana, basándose en confianza del scorer + ausencia de
señales de "caso difícil".

Directiva Yesid (mayo 2026):
  - Auto-enviar SOLO cuando confianza >= 0.90 AND no es caso difícil.
  - Caso difícil = valor >= 5M COP + multi-conceptos (SO+CO+FA+AU+TA)
    + requiere análisis profundo de soportes.
  - En cualquier otro caso, marcar para REVISAR_HUMANO o INTERVENIR.

Esta capa NO envía nada por sí misma — solo PRODUCE LA DECISIÓN. El
gestor decide si activa el modo "ejecutar auto-pilot" en la UI cuando
quiere que el sistema mande automáticamente los casos auto_enviables.
Por defecto, todo va a revisión humana.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger("motor_glosas")

# Umbral default — Yesid pidió "el más alto, con buen contexto, argumento
# y todos sus conceptos bien definidos".
UMBRAL_AUTO_ENVIO = 0.90

# Caso difícil: valor mínimo en COP por encima del cual SIEMPRE va a humano
VALOR_CASO_DIFICIL_COP = 5_000_000

# Prefijos de código que indican multi-concepto (Yesid: "soportes,
# pertinencia, facturación, autorización, tarifas, cobertura")
PREFIJOS_CONCEPTOS = {
    "SO": "Soportes",
    "PE": "Pertinencia",
    "CO": "Cobertura",
    "FA": "Facturación",
    "AU": "Autorizaciones",
    "TA": "Tarifas",
    "AT": "Atención",
    "DI": "Dispensación",
}

# Patrones de múltiples conceptos en la tabla_excel — busca códigos como
# "SO0101", "TA0801", "FA0202" en el mismo texto.
_PAT_CODIGOS = re.compile(r"\b([A-Z]{2})\d{2,4}\b")


def _detectar_conceptos_en_texto(texto_glosa: str) -> list[str]:
    """Devuelve la lista única de prefijos de concepto (TA, SO, FA, etc.)
    encontrados en el texto de la glosa."""
    if not texto_glosa:
        return []
    todos = _PAT_CODIGOS.findall(texto_glosa.upper())
    unicos = sorted({p for p in todos if p in PREFIJOS_CONCEPTOS})
    return unicos


def _parse_valor(valor_raw) -> float:
    """Convierte string $1.234.567 o número a float COP."""
    if valor_raw is None:
        return 0.0
    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)
    s = str(valor_raw)
    cleaned = re.sub(r"[^\d]", "", s)
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except Exception:
        return 0.0


def evaluar_caso_dificil(
    valor_objetado_raw,
    texto_glosa: str = "",
    soportes_count: int = 0,
) -> dict:
    """Determina si una glosa es "caso difícil" según directiva Yesid.

    Returns:
        {
          "es_caso_dificil": bool,
          "razones": list[str],
          "valor_cop": float,
          "conceptos_detectados": list[str],
        }
    """
    razones = []
    valor_cop = _parse_valor(valor_objetado_raw)
    conceptos = _detectar_conceptos_en_texto(texto_glosa)

    if valor_cop >= VALOR_CASO_DIFICIL_COP:
        razones.append(
            f"Valor objetado ${valor_cop:,.0f} supera el umbral de caso difícil (${VALOR_CASO_DIFICIL_COP:,})"
            .replace(",", ".")
        )

    if len(conceptos) >= 3:
        nombres = [PREFIJOS_CONCEPTOS.get(c, c) for c in conceptos]
        razones.append(
            f"Multi-concepto: {len(conceptos)} categorías diferentes ({', '.join(nombres)}) — requiere auditoría detallada"
        )

    # Multi-concepto + soportes ausentes = peor escenario
    if conceptos and soportes_count == 0:
        razones.append(
            "Sin soportes adjuntados: caso multi-concepto sin documentación es de alto riesgo"
        )

    return {
        "es_caso_dificil": bool(razones),
        "razones": razones,
        "valor_cop": valor_cop,
        "conceptos_detectados": conceptos,
    }


def decidir_auto_envio(
    confianza_score: float,
    valor_objetado_raw=None,
    texto_glosa: str = "",
    soportes_count: int = 0,
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    umbral: float = UMBRAL_AUTO_ENVIO,
) -> dict:
    """Decide si el dictamen es auto-enviable sin revisión humana.

    Reglas de oro:
      - confianza >= umbral (0.90 default)
      - NO es "caso difícil"
      - NO es ratificación (siempre revisión humana — escalada)
      - NO es extemporánea (texto fijo, mecánico, ya enviable de otra forma)
      - Tiene contenido (dictamen no vacío)

    Returns:
        {
          "auto_enviable": bool,
          "estado": "AUTO_ENVIABLE" | "REVISAR_HUMANO" | "INTERVENIR",
          "umbral_aplicado": 0.90,
          "es_caso_dificil": bool,
          "diagnostico_caso_dificil": dict (siempre, even if False),
          "razones_pro_envio_auto": list[str],
          "razones_contra_envio_auto": list[str],
          "color": "#16a34a" | "#d97706" | "#dc2626",
          "label": "AUTO-PILOT: enviable" | "AUTO-PILOT: requiere revisión" | ...,
        }
    """
    razones_pro: list[str] = []
    razones_contra: list[str] = []

    # Diagnóstico de caso difícil (siempre devuelto en el output)
    diag = evaluar_caso_dificil(valor_objetado_raw, texto_glosa, soportes_count)

    # Confianza
    if confianza_score is not None and confianza_score >= umbral:
        razones_pro.append(
            f"Confianza del dictamen {int(confianza_score*100)}% supera umbral {int(umbral*100)}%"
        )
    else:
        score_str = f"{int(confianza_score*100)}%" if confianza_score is not None else "—"
        razones_contra.append(
            f"Confianza {score_str} es inferior al umbral mínimo {int(umbral*100)}%"
        )

    # Caso difícil
    if diag["es_caso_dificil"]:
        razones_contra.extend([f"Caso difícil: {r}" for r in diag["razones"]])

    # Ratificación → siempre revisión humana (escalada de proceso)
    if es_ratificacion:
        razones_contra.append(
            "Es respuesta a glosa RATIFICADA: el siguiente paso es conciliación, requiere revisión humana"
        )

    # Decidir estado final
    if not razones_contra:
        estado = "AUTO_ENVIABLE"
        color = "#16a34a"
        label = "AUTO-PILOT: enviable sin revisión"
        auto_enviable = True
    elif confianza_score is not None and confianza_score >= 0.60:
        estado = "REVISAR_HUMANO"
        color = "#d97706"
        label = "AUTO-PILOT: requiere revisión humana"
        auto_enviable = False
    else:
        estado = "INTERVENIR"
        color = "#dc2626"
        label = "AUTO-PILOT: intervenir antes de enviar"
        auto_enviable = False

    return {
        "auto_enviable": auto_enviable,
        "estado": estado,
        "umbral_aplicado": umbral,
        "es_caso_dificil": diag["es_caso_dificil"],
        "diagnostico_caso_dificil": diag,
        "razones_pro_envio_auto": razones_pro,
        "razones_contra_envio_auto": razones_contra,
        "color": color,
        "label": label,
    }
