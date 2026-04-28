"""Auto-piloto graduado por confianza — clasifica cada glosa en uno de tres
niveles para que el gestor sepa cuánta intervención necesita.

Niveles:
  1. AUTO_RADICAR — confianza >98%, casos mecánicos (extemporáneas con
     >20 días, ratificadas en etapa de ratificación con texto canónico
     ya aplicado, glosas con tarifa pactada exacta y match perfecto).
     La IA puede generar y marcar como RESPONDIDA sin intervención —
     solo notificar al gestor. Hoy NO hacemos auto-radicación; el nivel
     existe para que la UI marque estas glosas como "1 click → listo".
  2. REVISAR_RAPIDO — confianza 85-98%. Dictamen pre-redactado de buena
     calidad, el gestor revisa y aprueba (botón "Aceptar y radicar").
  3. EDITAR_MANUAL — confianza <85% o casos atípicos. Editor completo,
     refinamientos, decisión humana.

Filosofía: el gestor decide cuánto intervenir; el motor le ahorra el
60% mecánico. Cada glosa trae su nivel pintado en la lista para que se
sepa de un vistazo qué hacer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Umbrales de confianza
UMBRAL_AUTO = 98
UMBRAL_REVISAR = 85


def clasificar_nivel(glosa, db) -> dict:
    """Clasifica una glosa en un nivel de auto-piloto y devuelve un dict
    con metadata para la UI:

        {
          "nivel": "AUTO_RADICAR" | "REVISAR_RAPIDO" | "EDITAR_MANUAL",
          "icono": "🤖" | "⚡" | "✏",
          "color": "#10b981" | "#f59e0b" | "#6366f1",
          "etiqueta": "Mecánica — 1 click",
          "razon": "Extemporánea de 27 días con texto canónico aplicado",
          "confianza_pct": 99,
          "accion_sugerida": "marcar_respondida" | "revisar" | "editar",
        }
    """
    from app.services.dictamen_stale import (
        _CANONICA_EXTEMPORANEA, _CANONICA_RATIFICADA,
        _INDICADORES_RATIFICACION, _texto_dictamen_normalizado,
        _eps_tiene_tarifas,
    )

    dictamen = (getattr(glosa, "dictamen", "") or "").strip()
    texto = _texto_dictamen_normalizado(dictamen) if dictamen else ""
    cod_glosa = (getattr(glosa, "codigo_glosa", "") or "").upper().strip()
    cod_resp = (getattr(glosa, "codigo_respuesta", "") or "").upper().strip()
    etapa = (getattr(glosa, "etapa", "") or "").upper()
    score = float(getattr(glosa, "score", 0) or 0)
    dias_radic = int(getattr(glosa, "dias_radicacion_dgh", 0) or 0)
    eps = (getattr(glosa, "eps", "") or "").strip()
    tercero = (getattr(glosa, "tercero_nombre", "") or "").strip()
    valor = float(getattr(glosa, "valor_objetado", 0) or 0)

    # Nivel 1: AUTO_RADICAR (mecánicas con texto canónico ya aplicado)
    if dias_radic > 20 and _CANONICA_EXTEMPORANEA in texto and cod_resp == "RE9502":
        return {
            "nivel": "AUTO_RADICAR",
            "icono": "🤖",
            "color": "#10b981",
            "etiqueta": "Mecánica — extemporánea",
            "razon": f"Extemporánea ({dias_radic} días) con texto canónico HUS aplicado y RE9502.",
            "confianza_pct": 99,
            "accion_sugerida": "marcar_respondida",
        }
    if any(ind in etapa for ind in _INDICADORES_RATIFICACION) and _CANONICA_RATIFICADA in texto and cod_resp == "RE9901":
        return {
            "nivel": "AUTO_RADICAR",
            "icono": "🤖",
            "color": "#10b981",
            "etiqueta": "Mecánica — ratificada",
            "razon": "Ratificación con texto canónico HUS aplicado y RE9901. Lista para conciliación.",
            "confianza_pct": 99,
            "accion_sugerida": "marcar_respondida",
        }
    # Tarifa con match exacto en contrato (info_tarifa con valor_pactado_calc
    # ≈ valor_facturado y RE coherente).
    if cod_glosa.startswith("TA") and dictamen and cod_resp == "RE9901":
        try:
            tarifa = _eps_tiene_tarifas(db, eps, tercero)
            if tarifa is not None and "TARIFA PACTADA" in texto:
                return {
                    "nivel": "AUTO_RADICAR",
                    "icono": "🤖",
                    "color": "#10b981",
                    "etiqueta": "Tarifa con contrato exacto",
                    "razon": "Tarifa pactada citada en el dictamen y RE9901 aplicado.",
                    "confianza_pct": 98,
                    "accion_sugerida": "marcar_respondida",
                }
        except Exception:
            pass

    # Nivel 2: REVISAR_RAPIDO (dictamen completo de calidad media-alta)
    if dictamen and len(dictamen) >= 800 and score >= UMBRAL_REVISAR:
        return {
            "nivel": "REVISAR_RAPIDO",
            "icono": "⚡",
            "color": "#f59e0b",
            "etiqueta": "Revisar y aprobar",
            "razon": f"Dictamen sólido (score {int(score)}, {len(dictamen)} chars). Revisar y radicar.",
            "confianza_pct": int(score) if score else 90,
            "accion_sugerida": "revisar",
        }

    # Nivel 3: EDITAR_MANUAL (casos atípicos, baja confianza, alta cuantía)
    razones = []
    if not dictamen:
        razones.append("sin dictamen generado")
    elif len(dictamen) < 500:
        razones.append(f"dictamen corto ({len(dictamen)} chars)")
    if score and score < UMBRAL_REVISAR:
        razones.append(f"score bajo ({int(score)})")
    if valor >= 5_000_000:
        razones.append(f"alta cuantía (${valor:,.0f})".replace(",", "."))
    if not cod_resp:
        razones.append("sin código RE")
    razon = "Requiere intervención humana: " + (", ".join(razones) if razones else "caso atípico")

    return {
        "nivel": "EDITAR_MANUAL",
        "icono": "✏",
        "color": "#6366f1",
        "etiqueta": "Editar manual",
        "razon": razon,
        "confianza_pct": int(score) if score else 60,
        "accion_sugerida": "editar",
    }
