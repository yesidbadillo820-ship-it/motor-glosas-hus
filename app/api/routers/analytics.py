from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import AnalyticsResult
from app.infrastructure.db.models import UsuarioRecord
from app.infrastructure.repositories.glosa_repository import GlosaRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/", response_model=AnalyticsResult)
def obtener_metricas_desempeno(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    repo = GlosaRepository(db)
    metrics = repo.metrics()
    
    return AnalyticsResult(
        glosas_mes=metrics["total"],
        valor_objetado_mes=metrics["valor_total"],
        valor_recuperado_mes=metrics["valor_recuperado"],
        tasa_exito_pct=metrics["tasa_recuperacion"],
    )


@router.get("/por-estado")
def analytics_por_estado(
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    metrics = repo.metrics()
    return metrics["por_estado"]


@router.get("/por-eps")
def analytics_por_eps(
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    metrics = repo.metrics()
    return metrics["por_eps"]
