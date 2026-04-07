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
    """
    Calcula en tiempo real:
    - Total de glosas procesadas.
    - Valor total objetado.
    - Valor recuperado (levantado).
    - Tasa de éxito porcentual.
    """
    repo = GlosaRepository(db)
    stats = repo.estadisticas()
    
    return AnalyticsResult(
        glosas_mes=stats.get("total", 0),
        valor_objetado_mes=stats.get("valor_objetado_total", 0),
        valor_recuperado_mes=stats.get("valor_recuperado_total", 0),
        tasa_exito_pct=stats.get("tasa_exito", 0),
    )


@router.get("/dashboard")
def dashboard(
    eps: str = None,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    from datetime import datetime, timedelta
    
    repo = GlosaRepository(db)
    stats = repo.estadisticas(eps)
    
    glosas = repo.listar(limit=1000, eps=eps)
    
    aging = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for g in glosas:
        dias = g.dias_restantes if g.dias_restantes > 0 else 0
        if dias <= 30:
            aging["0-30"] += 1
        elif dias <= 60:
            aging["31-60"] += 1
        elif dias <= 90:
            aging["61-90"] += 1
        else:
            aging["90+"] += 1
    
    eps_top = {}
    for g in glosas:
        eps_top[g.eps] = eps_top.get(g.eps, 0) + g.valor_objetado
    
    eps_ranking = sorted(eps_top.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "resumen": stats,
        "aging": aging,
        "top_eps_por_valor": [{"eps": e, "valor": v} for e, v in eps_ranking],
        "glosas_recientes": [
            {
                "id": g.id,
                "eps": g.eps,
                "paciente": g.paciente,
                "valor": g.valor_objetado,
                "estado": g.estado,
                "score": g.score,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
            }
            for g in glosas[:20]
        ],
    }