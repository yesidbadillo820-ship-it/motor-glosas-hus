from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import AnalyticsResult
from app.models.db import UsuarioRecord, GlosaRecord
from app.repositories.glosa_repository import GlosaRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/", response_model=AnalyticsResult)
def obtener_metricas_desempeno(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    repo = GlosaRepository(db)
    return repo.analytics()


@router.get("/por-estado")
def analytics_por_estado(
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    resultados = db.query(
        GlosaRecord.estado,
        func.count(GlosaRecord.id).label("cantidad"),
        func.sum(GlosaRecord.valor_objetado).label("valor_objetado"),
        func.sum(GlosaRecord.valor_aceptado).label("valor_aceptado"),
        func.avg(GlosaRecord.score).label("score_promedio"),
    ).group_by(GlosaRecord.estado).all()
    
    return [{"estado": r[0], "cantidad": r[1], "valor_objetado": float(r[2] or 0), "valor_aceptado": float(r[3] or 0), "score_promedio": float(r[4] or 0)} for r in resultados]


@router.get("/por-eps")
def analytics_por_eps(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    resultados = db.query(
        GlosaRecord.eps,
        func.count(GlosaRecord.id).label("cantidad"),
        func.sum(GlosaRecord.valor_objetado).label("valor_objetado"),
        func.sum(GlosaRecord.valor_aceptado).label("valor_aceptado"),
    ).group_by(GlosaRecord.eps).order_by(func.sum(GlosaRecord.valor_objetado).desc()).limit(limit).all()
    
    return [{"eps": r[0], "cantidad": r[1], "valor_objetado": float(r[2] or 0), "valor_aceptado": float(r[3] or 0)} for r in resultados]


@router.get("/aging")
def analytics_aging(
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    resultados = db.query(
        case(
            (GlosaRecord.dias_restantes <= 0, "VENCIDA"),
            (GlosaRecord.dias_restantes <= 30, "0-30"),
            (GlosaRecord.dias_restantes <= 60, "30-60"),
            else_="60+",
        ).label("rango"),
        func.count(GlosaRecord.id).label("cantidad"),
        func.sum(GlosaRecord.valor_objetado).label("valor"),
    ).group_by("rango").all()
    
    return [{"rango": r[0], "cantidad": r[1], "valor": float(r[2] or 0)} for r in resultados]


@router.get("/score")
def analytics_score(
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    resultados = db.query(
        case(
            (GlosaRecord.score >= 70, "URGENTE"),
            (GlosaRecord.score >= 40, "MEDIA"),
            else_="BAJA",
        ).label("prioridad"),
        func.count(GlosaRecord.id).label("cantidad"),
        func.sum(GlosaRecord.valor_objetado).label("valor"),
    ).group_by("prioridad").all()
    
    return [{"prioridad": r[0], "cantidad": r[1], "valor": float(r[2] or 0)} for r in resultados]
