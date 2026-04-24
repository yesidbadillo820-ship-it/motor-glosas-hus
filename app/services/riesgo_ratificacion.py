"""
riesgo_ratificacion.py — Indicador heurístico de riesgo de ratificación
========================================================================
Calcula la probabilidad de que una EPS ratifique la glosa (no levante)
con base en señales del texto, el código, la EPS y el contrato.

Score 0-100 donde:
  • 0-30:  BAJO (verde) — probable levantamiento
  • 31-60: MEDIO (ámbar) — requiere refuerzo
  • 61-100: ALTO (rojo) — alta probabilidad de ratificación
"""
from __future__ import annotations
from typing import Optional


# Factores de riesgo por código de glosa (según histórico nacional)
RIESGO_BASE_POR_CODIGO: dict[str, int] = {
    # Pertinencia clínica — altamente subjetivas, EPS suele ratificar
    "CL": 55, "PE": 55,
    # Autorización — si hay urgencia, casi siempre levantan; si no, riesgo medio
    "AU": 40,
    # Tarifas — depende del contrato
    "TA": 35,
    # Soportes — si están completos, bajo riesgo
    "SO": 30,
    # Cobertura — generalmente bajo riesgo si es PBS
    "CO": 30,
    # Facturación — formales subsanables
    "FA": 25,
    # Insumos / Medicamentos — variable
    "IN": 40, "ME": 40,
    # Extemporánea — casi siempre levantan si pasa el plazo
    "EX": 10,
}

EPS_HISTORICAMENTE_DIFICILES = {
    "NUEVA EPS", "SALUD TOTAL", "MEDIMAS", "SURA", "SANITAS",
}


def calcular_riesgo(
    codigo_glosa: str,
    eps: str,
    tiene_contrato: bool,
    tiene_pdf_soportes: bool,
    texto_glosa: str,
    es_extemporanea: bool,
    es_ratificacion: bool,
    score_dictamen: Optional[float] = None,
) -> dict:
    """Retorna {score, nivel, color, etiqueta, factores} con el riesgo estimado."""

    prefijo = (codigo_glosa or "")[:2].upper()
    score = RIESGO_BASE_POR_CODIGO.get(prefijo, 40)
    factores: list[str] = []

    # Ajuste por EPS
    eps_up = (eps or "").upper()
    if any(d in eps_up for d in EPS_HISTORICAMENTE_DIFICILES):
        score += 10
        factores.append("EPS con historial de ratificaciones frecuentes (+10)")

    # Ajuste por contrato
    if tiene_contrato:
        score -= 10
        factores.append("Existe contrato pactado (-10)")
    else:
        score += 8
        factores.append("Sin contrato vigente — defensa por SOAT pleno (+8)")

    # Ajuste por soportes
    if tiene_pdf_soportes:
        score -= 12
        factores.append("Soportes PDF adjuntos (-12)")
    else:
        score += 10
        factores.append("Sin soportes PDF adjuntos (+10)")

    # Casos especiales
    if es_extemporanea:
        score -= 25
        factores.append("Glosa extemporánea — silencio positivo (-25)")

    if es_ratificacion:
        score += 15
        factores.append("Es ratificación (segunda vuelta) (+15)")

    # Ajuste por score del dictamen (checklist pre-radicación)
    if score_dictamen is not None:
        if score_dictamen >= 90:
            score -= 10
            factores.append(f"Dictamen con score {score_dictamen} (APROBADO) (-10)")
        elif score_dictamen < 60:
            score += 10
            factores.append(f"Dictamen con score {score_dictamen} (débil) (+10)")

    # Señales de riesgo en el texto de la glosa (keywords agresivas)
    texto_up = (texto_glosa or "").upper()
    if any(k in texto_up for k in ["NO PROCEDE", "NO APLICA", "NO CORRESPONDE", "IMPROCEDENTE"]):
        score += 5
        factores.append("Glosa con lenguaje asertivo de rechazo (+5)")

    if "URGENCIA" in texto_up or "URGENTE" in texto_up:
        if prefijo == "AU":
            score -= 20
            factores.append("Urgencia vital (AU) — levantamiento obligatorio (-20)")

    # Clamp 0-100
    score = max(0, min(100, score))

    # Nivel
    if score <= 30:
        nivel = "BAJO"
        color = "#059669"
        etiqueta = "Alta probabilidad de levantamiento"
        icon = "🟢"
    elif score <= 60:
        nivel = "MEDIO"
        color = "#d97706"
        etiqueta = "Requiere refuerzo argumentativo"
        icon = "🟡"
    else:
        nivel = "ALTO"
        color = "#dc2626"
        etiqueta = "Alta probabilidad de ratificación — preparar conciliación"
        icon = "🔴"

    return {
        "score": int(score),
        "nivel": nivel,
        "color": color,
        "etiqueta": etiqueta,
        "icon": icon,
        "factores": factores,
    }
