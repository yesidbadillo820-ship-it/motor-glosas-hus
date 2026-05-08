"""Prediccion de ratificacion + Coaching personalizado.

Predice probabilidad de ratificacion EPS basandose en histerica
combinada de (eps + codigo_glosa) y entrega recomendaciones para
reforzar la defensa antes de enviar.

Coaching: analiza el desempeno del usuario logueado y produce 3-5
acciones concretas para mejorar.
"""
from __future__ import annotations
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord


router = APIRouter(prefix="/prediccion-ia", tags=["prediccion-ia"])


@router.get("/probabilidad-ratificacion")
def probabilidad_ratificacion(
    eps: str = Query(..., min_length=2),
    codigo: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Calcula probabilidad de RATIFICACION basada en histerica de la
    combinacion (eps, codigo_glosa) en los ultimos 12 meses.

    Returns:
        {
            "probabilidad_ratificacion_pct": 0-100,
            "muestra_total": int,
            "ratificadas": int,
            "levantadas": int,
            "ventana_dias": 365,
            "confianza": "baja" | "media" | "alta",
            "recomendaciones": [str, ...]
        }
    """
    desde = ahora_utc() - timedelta(days=365)
    rows = (
        db.query(
            func.count(GlosaRecord.id).label("total"),
            func.sum(case((GlosaRecord.decision_eps == "RATIFICADA", 1), else_=0)).label("ratif"),
            func.sum(case((GlosaRecord.decision_eps == "LEVANTADA", 1), else_=0)).label("lev"),
            func.coalesce(func.sum(GlosaRecord.valor_objetado), 0).label("valor_total"),
            func.coalesce(func.sum(GlosaRecord.valor_recuperado), 0).label("valor_rec"),
        )
        .filter(GlosaRecord.eps.ilike(f"%{eps.strip()}%"))
        .filter(GlosaRecord.codigo_glosa == codigo.strip())
        .filter(GlosaRecord.decision_eps.isnot(None))
        .filter(GlosaRecord.creado_en >= desde)
        .first()
    )
    total = int(rows.total or 0)
    ratif = int(rows.ratif or 0)
    lev = int(rows.lev or 0)
    decididas = ratif + lev
    if decididas == 0:
        return {
            "eps": eps,
            "codigo": codigo,
            "probabilidad_ratificacion_pct": None,
            "muestra_total": total,
            "ratificadas": ratif,
            "levantadas": lev,
            "ventana_dias": 365,
            "confianza": "sin_datos",
            "recomendaciones": [
                "No hay decisiones EPS para esta combinacion en los ultimos 12 meses.",
                "El dictamen sera la primera referencia historica - documenta el caso con detalle.",
            ],
        }
    prob = round(100 * ratif / decididas, 1)
    confianza = "alta" if decididas >= 20 else ("media" if decididas >= 8 else "baja")

    recos: list[str] = []
    if prob >= 60:
        recos.append(f"Alto riesgo: {prob}% de ratificacion historica. Considera tono FIRME.")
        recos.append("Reforza con citas literales a la HC indicando folios y fechas.")
        recos.append("Anexa Resolucion 2284/2023 art. 10-11 si aplica al codigo.")
    elif prob >= 35:
        recos.append(f"Riesgo moderado: {prob}% ratificacion. Tono DIPLOMATICO con base juridica solida.")
        recos.append("Asegurate de citar el contrato vigente con la EPS si tenes tarifa pactada.")
    else:
        recos.append(f"Bajo riesgo: solo {prob}% de ratificacion. Tono profesional estandar.")
        recos.append("Conserva la estructura habitual - los datos te respaldan.")

    if total > decididas:
        sin_decidir = total - decididas
        recos.append(f"Hay {sin_decidir} casos sin decision (en proceso) que pueden ajustar la prediccion.")

    return {
        "eps": eps,
        "codigo": codigo,
        "probabilidad_ratificacion_pct": prob,
        "muestra_total": total,
        "ratificadas": ratif,
        "levantadas": lev,
        "valor_total": float(rows.valor_total or 0),
        "valor_recuperado": float(rows.valor_rec or 0),
        "ventana_dias": 365,
        "confianza": confianza,
        "recomendaciones": recos,
    }


@router.get("/coaching")
async def coaching_personal(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Analiza el desempeno del usuario logueado en los ultimos 90
    dias y devuelve 3-5 acciones concretas para mejorar (heuristicas
    no-IA). Si Anthropic esta disponible y el usuario tiene >= 30
    glosas decididas, complementa con sugerencia generada por Claude.
    """
    desde = ahora_utc() - timedelta(days=90)
    # Stats personales
    rows = (
        db.query(
            func.count(GlosaRecord.id).label("total"),
            func.sum(case((GlosaRecord.decision_eps == "LEVANTADA", 1), else_=0)).label("lev"),
            func.sum(case((GlosaRecord.decision_eps == "RATIFICADA", 1), else_=0)).label("ratif"),
            func.coalesce(func.sum(GlosaRecord.valor_recuperado), 0).label("recuperado"),
            func.coalesce(func.sum(GlosaRecord.valor_objetado), 0).label("objetado"),
        )
        .filter(
            (GlosaRecord.auditor_email == current_user.email)
            | (GlosaRecord.gestor_nombre == current_user.email)
        )
        .filter(GlosaRecord.creado_en >= desde)
        .first()
    )
    total = int(rows.total or 0)
    lev = int(rows.lev or 0)
    ratif = int(rows.ratif or 0)
    decididas = lev + ratif
    pct_exito = round(100 * lev / decididas, 1) if decididas else 0

    # Promedio del equipo para comparar
    rows_team = (
        db.query(
            func.count(GlosaRecord.id).label("total"),
            func.sum(case((GlosaRecord.decision_eps == "LEVANTADA", 1), else_=0)).label("lev"),
            func.sum(case((GlosaRecord.decision_eps == "RATIFICADA", 1), else_=0)).label("ratif"),
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.decision_eps.isnot(None))
        .first()
    )
    team_total = int(rows_team.total or 0)
    team_lev = int(rows_team.lev or 0)
    team_ratif = int(rows_team.ratif or 0)
    team_decid = team_lev + team_ratif
    team_pct = round(100 * team_lev / team_decid, 1) if team_decid else 0

    # EPS donde mas perdes
    rows_eps = (
        db.query(
            GlosaRecord.eps,
            func.sum(case((GlosaRecord.decision_eps == "RATIFICADA", 1), else_=0)).label("ratif"),
            func.count(GlosaRecord.id).label("total"),
        )
        .filter(
            (GlosaRecord.auditor_email == current_user.email)
            | (GlosaRecord.gestor_nombre == current_user.email)
        )
        .filter(GlosaRecord.creado_en >= desde)
        .filter(GlosaRecord.decision_eps.isnot(None))
        .group_by(GlosaRecord.eps)
        .having(func.count(GlosaRecord.id) >= 3)
        .order_by(
            (
                func.sum(case((GlosaRecord.decision_eps == "RATIFICADA", 1), else_=0))
                * 1.0
                / func.count(GlosaRecord.id)
            ).desc()
        )
        .limit(3)
        .all()
    )

    acciones: list[dict] = []

    if total < 5:
        acciones.append({
            "icono": "i",
            "titulo": "Volumen muy bajo de actividad",
            "detalle": "Tenes solo "+str(total)+" glosas en los ultimos 90 dias. Considera tomar mas asignaciones para construir tu historico personal.",
            "prioridad": "info",
        })
    else:
        if pct_exito < team_pct - 5:
            acciones.append({
                "icono": "!",
                "titulo": f"Tu tasa de exito ({pct_exito}%) es {round(team_pct - pct_exito,1)} pts menor que el equipo",
                "detalle": f"El equipo promedia {team_pct}%. Revisa tus ratificaciones recientes y busca patrones de tono o argumentos faltantes.",
                "prioridad": "alta",
            })
        elif pct_exito > team_pct + 5:
            acciones.append({
                "icono": "+",
                "titulo": f"Estas {round(pct_exito - team_pct, 1)} pts arriba del equipo ({pct_exito}% vs {team_pct}%)",
                "detalle": "Tus dictamenes son referencia. Considera compartir tus mejores con el equipo (plantillas Gold).",
                "prioridad": "info",
            })

    for r in rows_eps:
        eps_name, ratif_n, total_n = r.eps, int(r.ratif or 0), int(r.total or 0)
        pct = round(100 * ratif_n / total_n, 1) if total_n else 0
        if pct >= 50 and total_n >= 3:
            acciones.append({
                "icono": "!",
                "titulo": f"{eps_name} te ratifica el {pct}% ({ratif_n}/{total_n})",
                "detalle": "Esta EPS aprende de tus argumentos y los rebate. Renueva tu plantilla, agrega jurisprudencia 2024-2025 y considera tono mas firme.",
                "prioridad": "alta",
            })

    if decididas >= 10:
        valor_recuperado = float(rows.recuperado or 0)
        valor_objetado = float(rows.objetado or 0)
        if valor_objetado > 0:
            recovery_rate = round(100 * valor_recuperado / valor_objetado, 1)
            if recovery_rate >= 65:
                acciones.append({
                    "icono": "*",
                    "titulo": f"Tasa de recuperacion en valor: {recovery_rate}%",
                    "detalle": "Por cada $100 objetados recuperas $"+str(round(recovery_rate))+". Excelente eficacia financiera.",
                    "prioridad": "info",
                })
            elif recovery_rate < 30:
                acciones.append({
                    "icono": "!",
                    "titulo": f"Tasa de recuperacion baja: {recovery_rate}%",
                    "detalle": "Identifica las glosas de alto valor que mas perdes y prioriza fortalecer ese tipo de defensas.",
                    "prioridad": "alta",
                })

    if not acciones:
        acciones.append({
            "icono": "+",
            "titulo": "Buen ritmo y calidad",
            "detalle": "No hay alertas relevantes. Mantene la consistencia y considera mentorear a otros gestores.",
            "prioridad": "info",
        })

    return {
        "ventana_dias": 90,
        "stats": {
            "total": total,
            "decididas": decididas,
            "levantadas": lev,
            "ratificadas": ratif,
            "pct_exito": pct_exito,
            "valor_recuperado": float(rows.recuperado or 0),
            "valor_objetado": float(rows.objetado or 0),
        },
        "team_pct_exito": team_pct,
        "team_decididas": team_decid,
        "acciones": acciones,
    }
