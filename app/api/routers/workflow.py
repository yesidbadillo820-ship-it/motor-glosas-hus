from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.glosa_repository import GlosaRepository
from app.services.workflow_service import WorkflowService, EstadoGlosa
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/workflow", tags=["workflow"])


class WorkflowUpdate(BaseModel):
    nuevo_estado: str
    nota: str = None


class WorkflowTransicion(BaseModel):
    hacia: str
    nota: str = None


class WorkflowTransicionLote(BaseModel):
    glosa_ids: list[int]
    hacia: str
    nota: str = None


@router.get("/{glosa_id}/estados")
def obtener_estados_disponibles(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Obtiene el estado actual y las transiciones válidas para una glosa.
    """
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    estado_actual = glosa.workflow_state or glosa.estado
    transiciones = WorkflowService.obtener_transiciones_validas(estado_actual)
    info_accion = WorkflowService.requiere_accion(estado_actual)
    
    return {
        "glosa_id": glosa_id,
        "estado_actual": estado_actual,
        "es_terminal": WorkflowService.es_terminal(estado_actual),
        "transiciones_validas": [
            {
                "hacia": t.hacia,
                "accion": t.accion,
                "requiere_nota": t.requiere_nota
            }
            for t in transiciones
        ],
        "info_accion": info_accion,
    }


@router.post("/{glosa_id}/transicionar")
def transicionar_glosa(
    glosa_id: int,
    data: WorkflowTransicion,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Transiciona una glosa a un nuevo estado.
    
    Estados válidos:
    - RADICADA → RESPONDIDA
    - RESPONDIDA → RATIFICADA, LEVANTADA, CONCILIADA
    - RATIFICADA → CONCILIADA, LEVANTADA, ESCALADA_SNS
    - CONCILIADA → LEVANTADA
    """
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    exito, mensaje = WorkflowService.transicionar(
        glosa=glosa,
        nuevo_estado=data.hacia.upper(),
        db=db,
        nota=data.nota,
        responsable=current_user.email,
    )
    
    if not exito:
        raise HTTPException(status_code=400, detail=mensaje)
    
    return {
        "success": True,
        "message": mensaje,
        "nuevo_estado": data.hacia.upper(),
        "glosa_id": glosa_id,
    }


@router.post("/transicionar-lote")
def transicionar_lote(
    data: WorkflowTransicionLote,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Transiciona en lote varias glosas al mismo estado.

    Idempotente: las que ya están en el estado destino se cuentan como
    `ya_en_estado` (no como fallidas). Útil para cerrar pendientes en bloque.
    Máximo 500 ids por llamada.
    """
    if not data.glosa_ids:
        raise HTTPException(400, "Lista de IDs vacía")
    if len(data.glosa_ids) > 500:
        raise HTTPException(400, "Máximo 500 glosas por lote")

    destino = (data.hacia or "").upper().strip()
    if not destino:
        raise HTTPException(400, "Estado destino requerido")

    repo = GlosaRepository(db)
    resumen = {
        "total": len(data.glosa_ids),
        "procesadas": 0,
        "ya_en_estado": 0,
        "fallidas": [],
    }
    nota = data.nota or f"Transición a {destino} en lote"

    for gid in data.glosa_ids:
        glosa = repo.obtener_por_id(gid)
        if not glosa:
            resumen["fallidas"].append({"id": gid, "error": "no encontrada"})
            continue
        estado_actual = (glosa.workflow_state or glosa.estado or "").upper()
        if estado_actual == destino:
            resumen["ya_en_estado"] += 1
            continue
        exito, mensaje = WorkflowService.transicionar(
            glosa=glosa,
            nuevo_estado=destino,
            db=db,
            nota=nota,
            responsable=current_user.email,
        )
        if exito:
            resumen["procesadas"] += 1
        else:
            # Race: si estado_actual cambió a destino entre la lectura y la
            # transición, el mensaje será "de {destino} a {destino}". Solo
            # ese patrón cuenta como idempotente; los demás (terminal
            # incompatible, etc.) son fallidas reales.
            msg = mensaje or ""
            if f"de {destino} a {destino}" in msg:
                resumen["ya_en_estado"] += 1
            else:
                resumen["fallidas"].append({"id": gid, "error": msg[:200]})

    return resumen


@router.get("/estados/definiciones")
def obtener_definiciones_estados(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """
    Retorna las definiciones de todos los estados del workflow.
    """
    estados = {}
    for estado in EstadoGlosa:
        estados[estado.value] = WorkflowService.requiere_accion(estado.value)
    
    return {"estados": estados}
