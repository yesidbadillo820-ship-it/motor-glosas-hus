from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.models.schemas import GlosaScoreResponse
from app.core.scoring import ScoringService
from app.core.observability import observability, metrics

router = APIRouter(prefix="/scoring", tags=["scoring"])
scoring_service = ScoringService()


@router.post("/calcular", response_model=GlosaScoreResponse)
def calcular_score(
    glosa_id: int,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    probabilidad = scoring_service.calcular_probabilidad_base(
        eps=glosa.eps,
        codigo_glosa=glosa.codigo_glosa or "",
        etapa=glosa.etapa or "INICIAL",
    )
    
    resultado = scoring_service.calcular(
        valor_objetado=glosa.valor_objetado,
        probabilidad_recuperacion=probabilidad,
        dias_restantes=glosa.dias_restantes,
        estado=glosa.estado_workflow or "RADICADA",
    )
    
    glosa.score = int(resultado.score)
    glosa.prioridad = resultado.prioridad
    db.commit()
    
    observability.log_info(
        f"Score calculado para glosa {glosa_id}",
        glosa_id=glosa_id,
        eps=glosa.eps,
        score=resultado.score,
        prioridad=resultado.prioridad
    )
    
    return GlosaScoreResponse(
        glosa_id=glosa_id,
        score=resultado.score,
        prioridad=resultado.prioridad,
        valor_ajustado=resultado.valor_ajustado,
        probabilidad_recuperacion=resultado.probabilidad_recuperacion,
        dias_hasta_vencimiento=resultado.dias_hasta_vencimiento,
    )


@router.get("/priorizar")
def listar_por_prioridad(
    limit: int = 50,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    from app.models.schemas import GlosaHistorialItem
    
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.estado.notin_(["CERRADA", "ACEPTADA", "RECHAZADA"]))
        .order_by(GlosaRecord.score.desc(), GlosaRecord.dias_restantes.asc())
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": g.id,
            "eps": g.eps,
            "paciente": g.paciente,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": g.valor_objetado,
            "score": g.score,
            "prioridad": g.prioridad,
            "dias_restantes": g.dias_restantes,
            "estado_workflow": g.estado_workflow,
        }
        for g in glosas
    ]


@router.post("/recalcular-todos")
def recalcular_todos(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    if usuario.rol != "admin":
        raise HTTPException(
            status_code=403,
            detail="Solo administradores pueden recalcular todos los scores"
        )
    
    glosas = db.query(GlosaRecord).filter(
        GlosaRecord.estado.notin_(["CERRADA", "ACEPTADA", "RECHAZADA"])
    ).all()
    
    actualizados = 0
    for glosa in glosas:
        probabilidad = scoring_service.calcular_probabilidad_base(
            eps=glosa.eps,
            codigo_glosa=glosa.codigo_glosa or "",
            etapa=glosa.etapa or "INICIAL",
        )
        
        resultado = scoring_service.calcular(
            valor_objetado=glosa.valor_objetado,
            probabilidad_recuperacion=probabilidad,
            dias_restantes=glosa.dias_restantes,
            estado=glosa.estado_workflow or "RADICADA",
        )
        
        glosa.score = int(resultado.score)
        glosa.prioridad = resultado.prioridad
        actualizados += 1
    
    db.commit()
    
    metrics.set("glosas_score_actualizados", actualizados)
    
    observability.log_info(
        f"Recalculados {actualizados} scores",
        usuario_id=usuario.id
    )
    
    return {"success": True, "actualizados": actualizados}