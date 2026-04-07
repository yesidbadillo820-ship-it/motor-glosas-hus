from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.api.deps import get_usuario_actual, get_db
from app.infrastructure.db.models import GlosaRecord, UsuarioRecord
from app.domain.services.workflow import WorkflowEngine, TransicionNoPermitida, EstadoGlosa
from app.domain.entities import Glosa
from app.infrastructure.external.observabilidad import observabilidad_logger

router = APIRouter(prefix="/workflow", tags=["workflow"])
workflow = WorkflowEngine()


class WorkflowTransition(BaseModel):
    glosa_id: int
    nuevo_estado: str


class WorkflowResponse(BaseModel):
    glosa_id: int
    estado_anterior: str
    estado_nuevo: str
    mensaje: str


@router.get("/estados")
def listar_estados():
    return workflow.obtener_todos_estados()


@router.post("/transicionar", response_model=WorkflowResponse)
def transicionar_glosa(
    transition: WorkflowTransition,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    glosa_db = db.query(GlosaRecord).filter(GlosaRecord.id == transition.glosa_id).first()
    if not glosa_db:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    estado_anterior = glosa_db.estado
    
    glosa = Glosa(
        id=glosa_db.id,
        eps=glosa_db.eps,
        estado=glosa_db.estado,
        responsable_id=glosa_db.responsable_id,
        fecha_estado=glosa_db.fecha_estado,
    )
    
    try:
        workflow.transicionar(glosa, transition.nuevo_estado, usuario.id)
    except TransicionNoPermitida as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    glosa_db.estado = glosa.estado
    glosa_db.fecha_estado = glosa.fecha_estado
    glosa_db.responsable_id = glosa.responsable_id
    db.commit()
    
    observabilidad_logger.log_workflow(
        glosa_db.id, estado_anterior, transition.nuevo_estado, usuario.id
    )
    
    return WorkflowResponse(
        glosa_id=glosa_db.id,
        estado_anterior=estado_anterior,
        estado_nuevo=transition.nuevo_estado,
        mensaje=f"Transición exitosa de {estado_anterior} a {transition.nuevo_estado}"
    )


@router.get("/sla/{glosa_id}")
def verificar_sla(
    glosa_id: int,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    glosa_db = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa_db:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    glosa = Glosa(
        id=glosa_db.id,
        estado=glosa_db.estado,
        fecha_estado=glosa_db.fecha_estado,
    )
    
    vencido = workflow.esta_vencido_sla(glosa)
    sla_actual = workflow.obtener_sla(EstadoGlosa(glosa_db.estado))
    
    return {
        "glosa_id": glosa_id,
        "estado": glosa_db.estado,
        "sla_horas": sla_actual.total_seconds() / 3600,
        "vencido": vencido
    }
