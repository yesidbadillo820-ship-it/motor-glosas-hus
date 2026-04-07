from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.api.deps import get_usuario_actual, get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.models.schemas import WorkflowTransition, GlosaDetail
from app.core.workflow import WorkflowEngine, EstadoWorkflow
from app.core.observability import observability, metrics

router = APIRouter(prefix="/workflow", tags=["workflow"])
workflow_engine = WorkflowEngine()


@router.post("/transicionar", response_model=dict)
def transicionar_glosa(
    transicion: WorkflowTransition,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == transicion.glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    try:
        estado_actual = EstadoWorkflow(glosa.estado_workflow or "RADICADA")
    except ValueError:
        estado_actual = EstadoWorkflow.RADICADA
    
    nuevo_estado = EstadoWorkflow(transicion.nuevo_estado.upper())
    
    if not workflow_engine.es_transicion_valida(estado_actual, nuevo_estado):
        raise HTTPException(
            status_code=400,
            detail=f"Transición no válida de {estado_actual.value} a {nuevo_estado.value}"
        )
    
    glosa.estado_workflow = nuevo_estado.value
    glosa.estado = nuevo_estado.value
    glosa.fecha_cambio_estado = datetime.now()
    glosa.responsable_id = usuario.id
    
    if transicion.motivo:
        glosa.comentario = transicion.motivo
    
    sla_fin = workflow_engine.calcular_sla(nuevo_estado, datetime.now())
    glosa.sla_vencimiento = sla_fin
    
    db.commit()
    
    observability.log_info(
        f"Glosa {glosa.id} transicionada a {nuevo_estado.value}",
        glosa_id=glosa.id,
        eps=glosa.eps,
        usuario_id=usuario.id,
        estado_anterior=estado_actual.value,
        estado_nuevo=nuevo_estado.value
    )
    
    metrics.increment("glosas_transicionadas")
    
    return {
        "success": True,
        "glosa_id": glosa.id,
        "estado_anterior": estado_actual.value,
        "estado_nuevo": nuevo_estado.value,
        "sla_vencimiento": sla_fin.isoformat()
    }


@router.get("/estados-validos/{estado_actual}")
def obtener_siguiente_estados(estado_actual: str):
    try:
        estado = EstadoWorkflow(estado_actual.upper())
        siguientes = workflow_engine.obtener_siguiente_estados(estado)
        return {
            "estado_actual": estado.value,
            "estados_siguientes": [s.value for s in siguientes]
        }
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Estado '{estado_actual}' no válido"
        )


@router.get("/sla/{glosa_id}")
def obtener_sla(glosa_id: int, db: Session = Depends(get_db)):
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    if not glosa.sla_vencimiento:
        return {
            "glosa_id": glosa_id,
            "sla_activo": False,
            "mensaje": "No hay SLA definido"
        }
    
    esta_vencido = workflow_engine.esta_vencido(glosa.sla_vencimiento)
    dias_restantes = workflow_engine.obtener_tiempo_restante(glosa.sla_vencimiento)
    
    return {
        "glosa_id": glosa_id,
        "sla_activo": True,
        "sla_vencimiento": glosa.sla_vencimiento.isoformat(),
        "esta_vencido": esta_vencido,
        "dias_restantes": dias_restantes,
        "estado": glosa.estado_workflow
    }


@router.get("/glosas-vencidas")
def glosas_vencidas(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    desde = datetime.now()
    glosas = (
        db.query(GlosaRecord)
        .filter(
            GlosaRecord.sla_vencimiento < desde,
            GlosaRecord.estado_workflow.notin_(["CERRADA", "ACEPTADA", "RECHAZADA"])
        )
        .order_by(GlosaRecord.sla_vencimiento.asc())
        .all()
    )
    
    return [
        {
            "id": g.id,
            "eps": g.eps,
            "paciente": g.paciente,
            "valor": g.valor_objetado,
            "estado": g.estado_workflow,
            "sla_vencimiento": g.sla_vencimiento.isoformat() if g.sla_vencimiento else None,
            "dias_vencido": (desde - g.sla_vencimiento).days if g.sla_vencimiento else 0
        }
        for g in glosas
    ]