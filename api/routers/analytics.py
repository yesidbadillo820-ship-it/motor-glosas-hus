from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_usuario_actual, get_db
from models.schemas import AnalyticsResult
from models.db import UsuarioRecord
from repositories.glosa_repository import GlosaRepository

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
