"""Confianza visible (Capa de Vida, ronda 32).

Analiza un dictamen YA GENERADO y explica en qué se apoyó: contrato real,
soportes clínicos (folios), fundamento normativo. Función PURA y de
solo-lectura — no cambia el dictamen ni la generación; solo lee el texto y
devuelve una etiqueta explicable para que el motor deje de ser una caja
negra.

  analizar_confianza(dictamen, numero_contrato=..., score=...) -> dict
"""

from __future__ import annotations

import re

# Marcas de que el dictamen se apoyó en los SOPORTES del expediente.
_PAT_SOPORTES = re.compile(
    r"\bFOLIO\b|HISTORIA\s+CL[IÍ]NICA|\bEPICRISIS\b|\bH\.?C\.?\b|FURAT|"
    r"HOJA\s+DE\s+EVOLUCI[OÓ]N|\bRIPS\b|\bFEV\b|\bHEV\b|M[EÉ]DICO\s+TRATANTE",
    re.IGNORECASE,
)

# Marcas de fundamento NORMATIVO.
_PAT_NORMA = re.compile(
    r"\bLEY\s+\d{2,4}\b|RESOLUCI[OÓ]N\s+\d{3,4}|DECRETO\s+\d{3,4}|"
    r"SENTENCIA\s+[TC]-?\d|CIRCULAR\s+\d{2,3}|\bART[IÍ]?C?U?L?O?\.?\s*\d",
    re.IGNORECASE,
)

# Marca de tarifa pactada (defensa contractual fuerte).
_PAT_TARIFA_PACTADA = re.compile(
    r"TARIFA\s+PACTADA|CL[AÁ]USULA|INCORPORAD[OA]\s+AL\s+CONTRATO", re.IGNORECASE
)


def _cita_contrato(dictamen_up: str, numero_contrato: str) -> bool:
    """True si el dictamen cita el contrato real de la EPS o la tarifa pactada."""
    if _PAT_TARIFA_PACTADA.search(dictamen_up):
        return True
    if not numero_contrato:
        return False
    # Token distintivo del número de contrato (evita coincidencias triviales).
    for token in re.findall(r"[A-Z0-9][A-Z0-9./\-]{5,}", numero_contrato.upper()):
        if token in dictamen_up:
            return True
    return False


def analizar_confianza(dictamen, *, numero_contrato: str = "", score=None) -> dict:
    """Devuelve {nivel, resumen, fuentes, senales} para un dictamen.

    - nivel: "alta" | "media" | "baja"
    - fuentes: lista legible de en qué se apoyó
    - senales: banderas booleanas (para depurar / la UI)
    """
    texto = str(dictamen or "")
    texto_up = texto.upper()

    cita_contrato = _cita_contrato(texto_up, numero_contrato or "")
    cita_soportes = bool(_PAT_SOPORTES.search(texto))
    cita_norma = bool(_PAT_NORMA.search(texto))

    fuentes: list[str] = []
    if cita_contrato:
        fuentes.append("Contrato real de la EPS")
    if cita_soportes:
        fuentes.append("Soportes clínicos (folios/HC)")
    if cita_norma:
        fuentes.append("Fundamento normativo")

    # Señales fuertes = contrato o soportes (evidencia concreta del caso).
    fuertes = int(cita_contrato) + int(cita_soportes)
    try:
        score_val = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_val = None

    if fuertes >= 1 and cita_norma and (score_val is None or score_val >= 7):
        nivel = "alta"
    elif fuertes >= 1 or (cita_norma and (score_val is None or score_val >= 6)):
        nivel = "media"
    else:
        nivel = "baja"

    resumen = {
        "alta": "Confianza alta: el dictamen se apoya en evidencia concreta del caso.",
        "media": "Confianza media: hay fundamento, pero conviene revisar antes de radicar.",
        "baja": "Confianza baja: defensa genérica — revisá que cite contrato o soportes.",
    }[nivel]

    return {
        "nivel": nivel,
        "resumen": resumen,
        "fuentes": fuentes,
        "senales": {
            "cita_contrato": cita_contrato,
            "cita_soportes": cita_soportes,
            "cita_norma": cita_norma,
        },
    }
