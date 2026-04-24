"""Autopilot de recomendación (Ronda 18).

Combina TODO lo construido hasta ahora (ML predictor + plantillas Gold +
detector de anomalías + dictamen IA) para clasificar cada glosa en uno
de cuatro estados semánticos:

  LISTA_ENVIAR  → riesgo MUY_BAJO + plantilla Gold disponible + dictamen
                   OK + sin anomalías. Confianza ≥ 0.85. El auditor solo
                   revisa visualmente y clickea enviar.

  CASI_LISTA    → riesgo BAJO + (Gold O dictamen largo con citas) + sin
                   anomalías ALTA. Confianza 0.65-0.85. Revisión ligera.

  REVISAR       → riesgo MEDIO o dictamen corto/sin citas. Confianza
                   0.40-0.65. Leer completo antes de enviar.

  INTERVENIR    → riesgo ALTO/MUY_ALTO o anomalía ALTA o dictamen vacío.
                   Confianza < 0.40. Reescribir o descartar.

El objetivo del usuario fue: «la IA haga absolutamente todo y el gestor
solo tenga que revisar que todo se fue y está funcionando okay». Este
servicio cierra el ciclo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.db import GlosaRecord, PlantillaGoldRecord
from app.services.detector_anomalias import detectar_valor_anomalo
from app.services.ml_ratificacion import predecir_ratificacion


ESTADOS = ("LISTA_ENVIAR", "CASI_LISTA", "REVISAR", "INTERVENIR")


@dataclass
class AutopilotResult:
    estado: str
    confianza: float                # 0-1
    razones_a_favor: list[str] = field(default_factory=list)
    razones_en_contra: list[str] = field(default_factory=list)
    acciones_sugeridas: list[str] = field(default_factory=list)
    detalle: dict = field(default_factory=dict)


def _tiene_plantilla_gold(db: Session, eps: str, codigo: str) -> int:
    """Cuenta las plantillas Gold activas para (eps, codigo)."""
    if not eps or not codigo:
        return 0
    try:
        n = (
            db.query(func.count(PlantillaGoldRecord.id))
            .filter(PlantillaGoldRecord.eps.ilike(f"%{eps.upper()}%"))
            .filter(PlantillaGoldRecord.codigo_glosa == codigo.upper())
            .filter(PlantillaGoldRecord.activa == 1)
            .scalar()
        )
        return int(n or 0)
    except Exception:
        return 0


_RE_CITAS = re.compile(
    r"(Ley|Resoluci[óo]n|Decreto|Circular|Sentencia|Acuerdo|Art[íi]culo)\b",
    re.IGNORECASE,
)


def _calidad_dictamen(dictamen: str) -> dict:
    """Heurísticas simples sobre el HTML del dictamen."""
    if not dictamen:
        return {"longitud": 0, "citas": 0, "tiene_contenido": False}
    # Muy simple: contar citas regex en el HTML crudo
    citas = len(_RE_CITAS.findall(dictamen))
    longitud = len(dictamen)
    return {
        "longitud": longitud,
        "citas": citas,
        "tiene_contenido": longitud >= 400,
    }


def evaluar_glosa_autopilot(db: Session, glosa: GlosaRecord) -> AutopilotResult:
    """Evalúa una glosa y la clasifica en uno de los ESTADOS."""
    razones_pro: list[str] = []
    razones_contra: list[str] = []
    acciones: list[str] = []

    # 0) Atajo texto fijo: si el dictamen fue pre-rellenado como RATIFICADA
    # o EXTEMPORÁNEA (Ronda 21), el caso es mecánico y no requiere revisión
    # IA — LISTA_ENVIAR directo con confianza alta. Respeta la regla de
    # prioridad: RATIFICADA gana sobre EXTEMPORÁNEA.
    modelo_actual = (getattr(glosa, "modelo_ia", "") or "").lower()
    if "texto_fijo" in modelo_actual and (getattr(glosa, "dictamen", "") or "").strip():
        if "ratificada" in modelo_actual:
            tipo_tf = "RATIFICADA"
        elif "extemporanea" in modelo_actual:
            tipo_tf = "EXTEMPORANEA"
        else:
            tipo_tf = "TEXTO_FIJO"
        return AutopilotResult(
            estado="LISTA_ENVIAR",
            confianza=0.95,
            razones_a_favor=[
                f"Dictamen fijo {tipo_tf} — texto canónico institucional.",
                "No requiere revisión IA ni validación manual adicional.",
            ],
            razones_en_contra=[],
            acciones_sugeridas=["Revisar visualmente y enviar."],
            detalle={
                "texto_fijo": tipo_tf,
                "modelo_ia": modelo_actual,
            },
        )

    # 1) Predictor ML
    try:
        pred = predecir_ratificacion(db, glosa)
    except Exception:
        pred = {
            "probabilidad_ratificacion": 0.5,
            "nivel": "MEDIO",
            "factores_positivos": [],
            "factores_negativos": [],
            "acciones_sugeridas": [],
        }

    nivel_pred = pred.get("nivel", "MEDIO")
    prob = float(pred.get("probabilidad_ratificacion", 0.5))

    # 2) Plantilla Gold
    gold_count = _tiene_plantilla_gold(db, glosa.eps or "", glosa.codigo_glosa or "")
    if gold_count:
        razones_pro.append(f"{gold_count} plantilla(s) Gold activas (EPS+código).")
    else:
        razones_contra.append("Sin plantilla Gold histórica para esta EPS+código.")

    # 3) Calidad del dictamen
    q = _calidad_dictamen(glosa.dictamen or "")
    if not q["tiene_contenido"]:
        razones_contra.append("Dictamen corto o vacío (< 400 caracteres).")
        acciones.append("Regenerá el dictamen con la IA antes de enviar.")
    else:
        razones_pro.append(f"Dictamen con {q['longitud']} caracteres y {q['citas']} citas normativas.")

    # 4) Anomalía de valor
    anom = None
    try:
        anom = detectar_valor_anomalo(db, glosa)
    except Exception:
        pass
    if anom is not None and anom.severidad == "ALTA":
        razones_contra.append(f"⚠️ Valor atípico (z={anom.entidad.get('z_score')}σ).")
        acciones.append("Verificá el valor objetado — está > 5σ del histórico del CUPS.")

    # ─── Clasificación ───────────────────────────────────────────────────
    tiene_anomalia_alta = anom is not None and anom.severidad == "ALTA"

    if (
        nivel_pred == "MUY_BAJO"
        and gold_count >= 1
        and q["tiene_contenido"]
        and not tiene_anomalia_alta
    ):
        estado = "LISTA_ENVIAR"
        confianza = 0.90 - prob  # más bajo prob → más alta confianza
    elif (
        nivel_pred in ("MUY_BAJO", "BAJO")
        and q["tiene_contenido"]
        and not tiene_anomalia_alta
        and (gold_count >= 1 or q["citas"] >= 3)
    ):
        estado = "CASI_LISTA"
        confianza = 0.75 - prob * 0.5
    elif nivel_pred in ("ALTO", "MUY_ALTO") or not q["tiene_contenido"] or tiene_anomalia_alta:
        estado = "INTERVENIR"
        confianza = 0.30 + (prob if nivel_pred in ("ALTO", "MUY_ALTO") else 0.0)
        acciones.append("⚠️ Alta probabilidad de ratificación o calidad baja — reforzá argumentos.")
    else:
        estado = "REVISAR"
        confianza = 0.50

    # Clamp
    confianza = max(0.0, min(1.0, round(confianza, 3)))

    # Heredá las acciones sugeridas del predictor
    for a in pred.get("acciones_sugeridas", []):
        if a not in acciones:
            acciones.append(a)

    return AutopilotResult(
        estado=estado,
        confianza=confianza,
        razones_a_favor=razones_pro,
        razones_en_contra=razones_contra,
        acciones_sugeridas=acciones,
        detalle={
            "prediccion_ml": pred,
            "plantillas_gold": gold_count,
            "calidad_dictamen": q,
            "anomalia_valor": anom.__dict__ if anom else None,
        },
    )


def evaluar_bandeja(
    db: Session,
    auditor_email: Optional[str] = None,
    limite: int = 100,
) -> dict:
    """Corre el autopilot sobre la bandeja de un auditor (o todas si no hay
    email). Retorna el conteo por estado y la lista paginada."""
    q = db.query(GlosaRecord).filter(GlosaRecord.estado == "PENDIENTE")
    if auditor_email:
        q = q.filter(GlosaRecord.auditor_email == auditor_email)
    glosas = q.order_by(GlosaRecord.dias_restantes.asc()).limit(limite).all()

    resultados = []
    conteo = {e: 0 for e in ESTADOS}
    for g in glosas:
        res = evaluar_glosa_autopilot(db, g)
        conteo[res.estado] = conteo.get(res.estado, 0) + 1
        resultados.append({
            "glosa_id": g.id,
            "codigo": g.codigo_glosa,
            "eps": g.eps,
            "valor": g.valor_objetado,
            "dias_restantes": g.dias_restantes,
            "estado_autopilot": res.estado,
            "confianza": res.confianza,
            "razones_a_favor": res.razones_a_favor,
            "razones_en_contra": res.razones_en_contra,
            "acciones_sugeridas": res.acciones_sugeridas,
        })
    return {
        "auditor_email": auditor_email,
        "total_evaluadas": len(glosas),
        "conteo_por_estado": conteo,
        "glosas": resultados,
    }
