from fastapi import APIRouter, Depends
from app.infrastructure.repositories.glosa_repository import GlosaRepository
from app.models.schemas import AnalyticsResult, GlosaHistorialItem
from app.api.deps import get_usuario_actual, get_db
from app.models.db import UsuarioRecord


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/", response_model=AnalyticsResult)
def obtener_metricas(
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    glosas = repo.listar_todos(limite=1000)
    
    total = len(glosas)
    valor_objetado = sum(g.valor_objetado for g in glosas)
    valor_recuperado = sum(g.valor_aceptado for g in glosas)
    
    tasa_exito = (valor_recuperado / valor_objetado * 100) if valor_objetado > 0 else 0.0
    
    return AnalyticsResult(
        glosas_mes=total,
        valor_objetado_mes=valor_objetado,
        valor_recuperado_mes=valor_recuperado,
        tasa_exito_pct=round(tasa_exito, 2),
    )


@router.get("/por_eps")
def metricas_por_eps(
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    glosas = repo.listar_todos(limite=1000)
    
    por_eps = {}
    for g in glosas:
        eps = g.eps
        if eps not in por_eps:
            por_eps[eps] = {"total": 0, "objetado": 0.0, "recuperado": 0.0}
        por_eps[eps]["total"] += 1
        por_eps[eps]["objetado"] += g.valor_objetado
        por_eps[eps]["recuperado"] += g.valor_aceptado
    
    resultado = []
    for eps, datos in por_eps.items():
        tasa = (datos["recuperado"] / datos["objetado"] * 100) if datos["objetado"] > 0 else 0.0
        resultado.append({
            "eps": eps,
            "total": datos["total"],
            "objetado": datos["objetado"],
            "recuperado": datos["recuperado"],
            "tasa_exito": round(tasa, 2),
        })
    
    return sorted(resultado, key=lambda x: x["objetado"], reverse=True)


@router.get("/ aging")
def aging(
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    glosas = repo.listar_todos(limite=1000)
    
    aging = {"0-30": 0, "30-60": 0, "60+": 0, "vencidas": 0}
    
    for g in glosas:
        dias = g.dias_restantes
        if dias < 0:
            aging["vencidas"] += 1
        elif dias <= 30:
            aging["0-30"] += 1
        elif dias <= 60:
            aging["30-60"] += 1
        else:
            aging["60+"] += 1
    
    return aging