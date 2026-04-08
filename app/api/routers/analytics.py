from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.schemas import AnalyticsResult
from app.repositories.glosa_repository import GlosaRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/", response_model=AnalyticsResult)
def obtener_metricas_desempeno(
    db: Session = Depends(get_db),
):
    """
    Calcula en tiempo real:
    - Total de glosas procesadas.
    - Valor total objetado.
    - Valor recuperado (levantado).
    - Tasa de éxito porcentual.
    """
    repo = GlosaRepository(db)
    return repo.analytics()

@router.get("/metrics")
def obtener_metrics(
    db: Session = Depends(get_db),
):
    """Obtiene métricas por EPS y por estado"""
    repo = GlosaRepository(db)
    return repo.metrics()

@router.get("/tendencias")
def obtener_tendencias(
    meses: int = 6,
    db: Session = Depends(get_db),
):
    """Obtiene tendencias mensuales"""
    repo = GlosaRepository(db)
    return repo.tendencias_mensuales(meses)

@router.get("/top")
def obtener_top(
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """Obtiene top glosas por valor"""
    repo = GlosaRepository(db)
    return repo.top_glosas(limit)

@router.get("/reporte-ejecutivo")
def obtener_reporte_ejecutivo(
    db: Session = Depends(get_db),
):
    """Genera datos para reporte ejecutivo PDF"""
    repo = GlosaRepository(db)
    
    # Métricas generales
    analytics = repo.analytics()
    metrics = repo.metrics()
    tendencias = repo.tendencias_mensuales(6)
    top = repo.top_glosas(5)
    
    return {
        "resumen": {
            "total_glosas": analytics.glosas_mes,
            "valor_objetado": analytics.valor_objetado_mes,
            "valor_recuperado": analytics.valor_recuperado_mes,
            "tasa_exito": analytics.tasa_exito_pct,
        },
        "por_eps": metrics.get("by_eps", []),
        "por_estado": metrics.get("by_estado", []),
        "tendencias": tendencias,
        "top_glosas": top,
    }
