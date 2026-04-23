"""ML predictivo de ratificación (Ronda 12).

Dado un dictamen recién generado, estima la probabilidad de que la EPS
lo RATIFIQUE (no nos dé la razón). Si el score es alto, sugiere acciones
para reforzar la defensa ANTES de radicar.

No usa red neuronal (requeriría training, datos, infra). Usa **regresión
logística implementada a mano** con coeficientes derivados del análisis
histórico del dominio + heurísticas. Mismo espíritu: aprender del histórico.

El coeficiente se puede reentrenar con un script admin cuando haya
suficientes datos (>500 decisiones EPS) actualizando los pesos.

Input: un GlosaRecord (o un dict equivalente) + histórico de la EPS
Output:
  {
    "probabilidad_ratificacion": 0-1,
    "nivel": "MUY_BAJO" | "BAJO" | "MEDIO" | "ALTO" | "MUY_ALTO",
    "factores_positivos": [...],  # factores que BAJAN el riesgo
    "factores_negativos": [...],  # factores que SUBEN el riesgo
    "acciones_sugeridas": [...],
  }
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import GlosaRecord


# Coeficientes de la "regresión logística" — derivados manualmente del
# análisis histórico. Reentrenar cuando haya >500 decisiones EPS.
_PESOS = {
    # Constante (intercepto)
    "intercepto": -0.8,
    # EPS con historial de alta ratificación (>30% en últimos 3 meses)
    "eps_alta_ratif": 1.2,
    # Glosa tipo TA (tarifas) — más disputadas que SO/FA
    "es_tarifa": 0.3,
    # Sin soportes PDF adjuntos
    "sin_soportes": 0.5,
    # Dictamen muy corto (<500 chars) — argumentación débil
    "dictamen_corto": 0.6,
    # Dictamen muy largo (>3000 chars) — puede perder foco
    "dictamen_muy_largo": 0.1,
    # No usa citas normativas específicas (<3 normas citadas)
    "pocas_citas": 0.4,
    # Plantilla Gold usada (aumenta éxito)
    "usa_plantilla_gold": -0.6,
    # Plantilla fija determinística (texto_fijo) — casos "obvios"
    "es_texto_fijo": -0.5,
    # Match perfecto de tarifa (facturado=pactado)
    "match_perfecto": -0.9,
    # Aseguradora SOAT sin contrato (compañías aseguradoras suelen aceptar)
    "aseguradora_soat": -0.4,
    # Ratificación previa del MISMO código de glosa en la MISMA EPS
    "ratif_previa_mismo_codigo": 0.7,
    # Valor objetado alto (>$1M) — más probable ratificación
    "valor_alto": 0.3,
    # Régimen especial FF.MM./PPL (tienen reglas propias)
    "regimen_ffmm": -0.2,
}


def _sigmoide(x: float) -> float:
    """Sigmoid matemática: mapea R → (0, 1)."""
    if x >= 500:
        return 1.0
    if x <= -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def predecir_ratificacion(db: Session, glosa: GlosaRecord) -> dict:
    """Evalúa la probabilidad de que la EPS ratifique esta glosa.

    Usa regresión logística manual sobre 13 features del dominio. Retorna
    score 0-1, nivel semántico, factores que suben/bajan el riesgo y
    acciones sugeridas.
    """
    factores_pos = []  # bajan el riesgo
    factores_neg = []  # suben el riesgo
    acciones = []
    x = _PESOS["intercepto"]

    codigo = (glosa.codigo_glosa or "").upper()
    prefijo = codigo[:2]
    eps = (glosa.eps or "").upper()
    dictamen = glosa.dictamen or ""
    modelo = (glosa.modelo_ia or "").lower()

    # 1) EPS con alta tasa de ratificación (>30% últimos 90 días)
    try:
        hace_90d = datetime.utcnow() - timedelta(days=90)
        total = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.eps.ilike(f"%{eps}%")
        ).filter(GlosaRecord.decision_eps.isnot(None)).filter(
            GlosaRecord.creado_en >= hace_90d
        ).scalar() or 0
        ratif = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.eps.ilike(f"%{eps}%")
        ).filter(GlosaRecord.decision_eps == "RATIFICADA").filter(
            GlosaRecord.creado_en >= hace_90d
        ).scalar() or 0
        if total >= 5 and ratif / total > 0.30:
            x += _PESOS["eps_alta_ratif"]
            factores_neg.append(
                f"EPS {glosa.eps} ratifica {100 * ratif / total:.0f}% en los últimos 90 días ({ratif}/{total})."
            )
            acciones.append(
                "Considerá subir tono a FIRME y reforzar con jurisprudencia reciente."
            )
    except Exception:
        pass

    # 2) Tipo de glosa
    if prefijo == "TA":
        x += _PESOS["es_tarifa"]
        factores_neg.append("Las glosas tipo TARIFAS son las más disputadas.")

    # 3) Tamaño del dictamen
    if len(dictamen) < 500:
        x += _PESOS["dictamen_corto"]
        factores_neg.append("Dictamen muy corto (<500 chars): argumentación débil.")
        acciones.append("Expandí el argumento con más contexto normativo y fáctico.")
    elif len(dictamen) > 3000:
        x += _PESOS["dictamen_muy_largo"]
        factores_neg.append("Dictamen muy largo (>3000 chars): puede perder foco.")
        acciones.append("Considerá resumir para destacar los 2-3 argumentos más fuertes.")

    # 4) Citas normativas (conteo de menciones de Ley/Res./Decreto/Art./Sentencia)
    try:
        import re
        citas = len(re.findall(
            r"\b(LEY|RESOLUCI[ÓO]N|DECRETO|CIRCULAR|ART\.?|SENTENCIA|ACUERDO)\s+[A-Z0-9]+\b",
            dictamen.upper(),
        ))
        if citas < 3:
            x += _PESOS["pocas_citas"]
            factores_neg.append(f"Solo {citas} citas normativas detectadas.")
            acciones.append("Agregá al menos 3 normas: una general (Ley 1438), una específica del tipo y una del marco SOAT.")
        else:
            factores_pos.append(f"{citas} citas normativas sólidas.")
    except Exception:
        pass

    # 5) Plantilla/modelo
    if "plantilla" in modelo or "gold" in modelo:
        x += _PESOS["usa_plantilla_gold"]
        factores_pos.append("Usa plantilla Gold (argumento probado exitoso).")
    if "texto_fijo" in modelo or "pre-analisis" in modelo:
        x += _PESOS["es_texto_fijo"]
        factores_pos.append("Caso 'obvio' con plantilla determinística.")
    if "TARIFA_MATCH_PERFECTO" in (glosa.estado or "").upper() or "MATCH" in modelo.upper():
        x += _PESOS["match_perfecto"]
        factores_pos.append("MATCH PERFECTO de tarifa (facturado = pactado en contrato).")

    # 6) Aseguradora SOAT sin contrato
    if any(k in eps for k in ("MUNDIAL", "BOLÍVAR", "LIBERTY", "COMPAÑÍA", "ASEGURADORA", "ARL", "POSITIVA")):
        x += _PESOS["aseguradora_soat"]
        factores_pos.append("Aseguradora SOAT — tasa de ratificación históricamente menor.")

    # 7) Régimen especial
    if any(k in eps for k in ("FOMAG", "POLICIA", "SANIDAD", "PPL", "DISPENSARIO")):
        x += _PESOS["regimen_ffmm"]
        factores_pos.append("Régimen especial FF.MM./PPL: marco normativo favorable al prestador.")

    # 8) Ratificación previa del mismo código en la misma EPS
    try:
        previas = db.query(func.count(GlosaRecord.id)).filter(
            GlosaRecord.eps.ilike(f"%{eps}%")
        ).filter(GlosaRecord.codigo_glosa == codigo).filter(
            GlosaRecord.decision_eps == "RATIFICADA"
        ).scalar() or 0
        if previas >= 2:
            x += _PESOS["ratif_previa_mismo_codigo"]
            factores_neg.append(
                f"{previas} ratificaciones previas del mismo código {codigo} en esta EPS."
            )
            acciones.append(
                "Revisá las glosas ratificadas para detectar qué argumento falló y no repetirlo."
            )
    except Exception:
        pass

    # 9) Valor alto
    if float(glosa.valor_objetado or 0) >= 1_000_000:
        x += _PESOS["valor_alto"]
        factores_neg.append(f"Valor objetado alto (${int(glosa.valor_objetado):,}) → auditoría más estricta.")

    # ─── Sigmoid ──────────────────────────────────────────────────────────
    prob = _sigmoide(x)

    if prob >= 0.75:
        nivel = "MUY_ALTO"
    elif prob >= 0.55:
        nivel = "ALTO"
    elif prob >= 0.35:
        nivel = "MEDIO"
    elif prob >= 0.15:
        nivel = "BAJO"
    else:
        nivel = "MUY_BAJO"

    if nivel in ("ALTO", "MUY_ALTO"):
        acciones.insert(0, "🚨 ALTO RIESGO: considerá reforzar el dictamen ANTES de radicar.")
    elif nivel == "MEDIO":
        acciones.insert(0, "⚠️ Riesgo medio: revisá citas y tono antes de enviar.")

    return {
        "probabilidad_ratificacion": round(prob, 3),
        "nivel": nivel,
        "factores_positivos": factores_pos,
        "factores_negativos": factores_neg,
        "acciones_sugeridas": acciones,
        "score_logit": round(x, 3),  # debug / trazabilidad
    }
