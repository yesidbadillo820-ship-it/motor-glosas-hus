"""Auditoría automática del dictamen antes de marcarlo como RESPONDIDA.

Filosofía: no bloquear al gestor; sugerir. Si todo OK, pasa silenciosamente
y se marca RESPONDIDA. Si encuentra señales de problema, devuelve una lista
de hallazgos amigable que el gestor revisa y decide si corrige o continúa.

Cada hallazgo tiene severidad:
  - bloqueante (raro): error legal grave que la EPS rechazará. Solo dos:
    cita Art. 56 cuando debería ser 57, o RE incoherente con código glosa.
    Aún así NO bloquea técnicamente — se le muestra al gestor con "Confirmar
    de todos modos" para no frenar flujos legítimos.
  - alta: muy probable error (texto vacío, plazo mal calculado, etc.)
  - media: puede mejorar (sin tarifa cuando hay contrato, score bajo)
  - baja: tip educativo (sugerir tono distinto, plantilla Gold, etc.)

Cada hallazgo trae `tip` con la acción concreta que el gestor puede tomar.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models.db import GlosaRecord


_FRASES_ART_56_INCORRECTO = (
    "ART. 56 LEY 1438",
    "ARTICULO 56 LEY 1438",
    "ARTÍCULO 56 LEY 1438",
    "ART 56 LEY 1438",
)


def _norm(s: str) -> str:
    import re
    import unicodedata
    sin = re.sub(r"<[^>]+>", " ", s or "")
    nfkd = unicodedata.normalize("NFKD", sin)
    sin_dia = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_dia).strip().upper()


def auditar_dictamen(glosa, db) -> dict:
    """Audita el dictamen y devuelve hallazgos.

    Estructura del retorno:
        {
          "ok": bool,                # True si no hay hallazgos
          "puntaje": 0..100,         # qué tan saludable es el dictamen
          "hallazgos": [
            {
              "severidad": "alta"|"media"|"baja",
              "icono": "🔴"|"🟡"|"🔵"|"💡",
              "titulo": "Texto corto",
              "detalle": "Explicación amigable de qué pasa",
              "tip": "Acción sugerida",
              "campo": "dictamen"|"codigo_respuesta"|"plazo"|"tarifa"|"normas",
            }, ...
          ],
          "celebracion": str | None,  # mensaje positivo si todo OK
        }
    """
    hallazgos = []
    dictamen = (getattr(glosa, "dictamen", "") or "").strip()
    texto = _norm(dictamen)
    cod_resp = (getattr(glosa, "codigo_respuesta", "") or "").strip().upper()
    cod_glosa = (getattr(glosa, "codigo_glosa", "") or "").strip().upper()
    eps = (getattr(glosa, "eps", "") or "").strip()
    valor_obj = float(getattr(glosa, "valor_objetado", 0) or 0)

    # 1. Dictamen vacío o muy corto
    if not dictamen:
        hallazgos.append({
            "severidad": "alta",
            "icono": "🔴",
            "titulo": "Dictamen vacío",
            "detalle": "Esta glosa no tiene dictamen guardado.",
            "tip": "Pulsá 'Re-analizar con IA' para generarlo.",
            "campo": "dictamen",
        })
    elif len(dictamen) < 200:
        hallazgos.append({
            "severidad": "alta",
            "icono": "🔴",
            "titulo": "Dictamen muy corto",
            "detalle": f"Solo {len(dictamen)} caracteres — la EPS puede objetar por falta de motivación.",
            "tip": "Refiná con la IA para agregar fundamento técnico y normativo.",
            "campo": "dictamen",
        })

    # 2. Cita Art. 56 cuando debería ser Art. 57
    if any(f in texto for f in _FRASES_ART_56_INCORRECTO):
        hallazgos.append({
            "severidad": "alta",
            "icono": "🔴",
            "titulo": "Cita normativa incorrecta",
            "detalle": (
                "El dictamen cita Art. 56 Ley 1438/2011, pero el artículo "
                "que regula el trámite de glosas es el Art. 57. El Art. 56 "
                "regula otra materia."
            ),
            "tip": "Re-analizá para que la IA cite el artículo correcto.",
            "campo": "normas",
        })

    # 3. Coherencia de RE code (si hay código glosa TA y el cod_resp es RE9602
    #    pero hay tarifa pactada — sugerir RE9901)
    try:
        from app.services.dictamen_stale import _eps_tiene_tarifas
        if cod_resp == "RE9602" and cod_glosa.startswith("TA"):
            tercero = (getattr(glosa, "tercero_nombre", "") or "").strip()
            tarifa = _eps_tiene_tarifas(db, eps, tercero)
            if tarifa is not None:
                hallazgos.append({
                    "severidad": "alta",
                    "icono": "🔴",
                    "titulo": "Código RE9602 con contrato existente",
                    "detalle": (
                        "RE9602 ('injustificada con evidencia') aplica cuando "
                        "no hay contrato pactado. Pero esta EPS sí tiene tarifa "
                        "cargada en el catálogo — el código correcto es RE9901."
                    ),
                    "tip": "Re-analizá la glosa para que use RE9901 + cite el contrato.",
                    "campo": "codigo_respuesta",
                })
    except Exception:
        pass

    # 4. Texto canónico extemporánea / ratificada
    try:
        from app.services.dictamen_stale import (
            _CANONICA_EXTEMPORANEA, _CANONICA_RATIFICADA, _INDICADORES_RATIFICACION,
        )
        dias = int(getattr(glosa, "dias_radicacion_dgh", 0) or 0)
        etapa = (getattr(glosa, "etapa", "") or "").upper()
        if dias > 20 and _CANONICA_EXTEMPORANEA not in texto:
            hallazgos.append({
                "severidad": "alta",
                "icono": "🔴",
                "titulo": "Extemporánea sin texto canónico",
                "detalle": (
                    f"La glosa es extemporánea ({dias} días) pero el dictamen no usa "
                    "el texto fijo institucional HUS para extemporáneas."
                ),
                "tip": "Re-analizá: la IA debería aplicar el texto fijo automáticamente.",
                "campo": "dictamen",
            })
        if any(ind in etapa for ind in _INDICADORES_RATIFICACION) and _CANONICA_RATIFICADA not in texto:
            hallazgos.append({
                "severidad": "alta",
                "icono": "🔴",
                "titulo": "Ratificada sin texto canónico",
                "detalle": (
                    "La glosa está en etapa de ratificación pero el dictamen "
                    "no usa el texto fijo institucional HUS."
                ),
                "tip": "Re-analizá para aplicar el texto canónico de ratificación.",
                "campo": "dictamen",
            })
    except Exception:
        pass

    # 5. Sin código de respuesta
    if not cod_resp:
        hallazgos.append({
            "severidad": "media",
            "icono": "🟡",
            "titulo": "Falta código de respuesta",
            "detalle": "No hay RE code asignado — el export DGH lo necesita.",
            "tip": "Re-analizá o asigná manualmente un código de respuesta.",
            "campo": "codigo_respuesta",
        })

    # 6. Glosa de alta cuantía sin normas citadas
    normas_palabra = ("LEY ", "DECRETO", "RESOLUCION", "RESOLUCIÓN",
                      "ARTICULO", "ARTÍCULO", "ART.", "CIRCULAR")
    cuantas_normas = sum(texto.count(n) for n in normas_palabra)
    if valor_obj >= 5_000_000 and cuantas_normas < 3:
        hallazgos.append({
            "severidad": "media",
            "icono": "🟡",
            "titulo": "Alta cuantía con poca fundamentación",
            "detalle": (
                f"Glosa de ${valor_obj:,.0f} con solo {cuantas_normas} citas "
                "normativas. La EPS suele exigir mayor sustento en estos casos."
            ).replace(",", "."),
            "tip": "Refiná con la IA para reforzar la argumentación legal.",
            "campo": "normas",
        })

    # Puntaje saludable: 100 - 30 por cada hallazgo alta - 10 por media - 0 por baja
    pesos = {"alta": 30, "media": 10, "baja": 0}
    puntaje = max(0, 100 - sum(pesos.get(h["severidad"], 0) for h in hallazgos))

    celebracion = None
    if not hallazgos:
        celebracion = (
            "✨ Dictamen impecable — está listo para radicar a la EPS."
        )

    return {
        "ok": len(hallazgos) == 0,
        "puntaje": puntaje,
        "hallazgos": hallazgos,
        "celebracion": celebracion,
    }
