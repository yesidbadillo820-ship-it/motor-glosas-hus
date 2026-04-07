from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.interfaces.api.deps import get_usuario_actual, get_db
from app.domain.value_objects.schemas import AnalyticsResult
from app.domain.entities.db import UsuarioRecord
from app.infrastructure.repositories.glosa_repository import GlosaRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/", response_model=AnalyticsResult)
def obtener_metricas_desempeno(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
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
