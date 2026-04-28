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


class ReabrirParaCorregirInput(BaseModel):
    glosa_ids: list[int]
    motivo: str = "Reabrir para corregir dictamen"


@router.post("/reabrir-para-corregir")
def reabrir_para_corregir(
    data: ReabrirParaCorregirInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Reabre glosas en estado RESPONDIDA / CONCILIADA para que puedan ser
    corregidas (re-analizadas con la IA) y luego volver a marcarse como
    respondidas. Usado cuando el dictamen original quedó mal por error de
    auditor o por falta de contrato cargado al momento.

    No toca decision_eps ni los registros ya enviados a la EPS — solo
    revierte el estado interno del workflow para permitir la corrección.
    Máx 200 ids por llamada. Idempotente: las que no estaban en RESPONDIDA
    ni CONCILIADA se ignoran.
    """
    if not data.glosa_ids:
        raise HTTPException(400, "Lista de IDs vacía")
    if len(data.glosa_ids) > 200:
        raise HTTPException(400, "Máximo 200 glosas por reapertura")

    repo = GlosaRepository(db)
    estados_reabribles = {"RESPONDIDA", "CONCILIADA"}
    resumen = {
        "total": len(data.glosa_ids),
        "reabiertas": 0,
        "ya_no_estaban_cerradas": 0,
        "fallidas": [],
    }
    nota = (data.motivo or "Reabrir para corregir dictamen")[:500]

    for gid in data.glosa_ids:
        glosa = repo.obtener_por_id(gid)
        if not glosa:
            resumen["fallidas"].append({"id": gid, "error": "no encontrada"})
            continue
        wf_actual = (glosa.workflow_state or "").upper()
        est_actual = (glosa.estado or "").upper()
        if wf_actual not in estados_reabribles and est_actual not in estados_reabribles:
            resumen["ya_no_estaban_cerradas"] += 1
            continue
        # Revertir a RADICADA — no usamos WorkflowService.transicionar
        # porque la transición RESPONDIDA → RADICADA no está en el grafo
        # válido. Lo hacemos directamente con auditoría explícita.
        glosa.workflow_state = "RADICADA"
        if est_actual in estados_reabribles:
            glosa.estado = "RADICADA"
        glosa.nota_workflow = nota
        resumen["reabiertas"] += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error al guardar: {e}")

    # Auditoría: una sola entrada agregada
    try:
        from app.repositories.audit_repository import AuditRepository
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="REABRIR_PARA_CORREGIR",
            tabla="historial",
            detalle=(
                f"total={resumen['total']} reabiertas={resumen['reabiertas']} "
                f"motivo='{nota[:100]}'"
            ),
        )
    except Exception:
        pass

    return resumen


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
            # "RESPONDIDA a RESPONDIDA" y similares se tratan como idempotentes
            if "a " + destino in (mensaje or "") and destino in (mensaje or ""):
                resumen["ya_en_estado"] += 1
            else:
                resumen["fallidas"].append({"id": gid, "error": mensaje[:200]})

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
