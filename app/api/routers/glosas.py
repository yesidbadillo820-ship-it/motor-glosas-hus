import re
import uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse

from app.database import get_db
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.contrato_repository import ContratoRepository
from app.services.glosa_service import GlosaService
from app.services.pdf_service import PdfService
from app.core.config import get_settings
from app.core.logging_utils import set_request_id, get_request_id, logger
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/glosas", tags=["glosas"])


@router.get("/historial", response_model=list)
def historial(
    limit: int = 50,
    eps:   Optional[str] = None,
    db:    Session        = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosas = repo.listar(limit=limit, eps=eps)
    return [
        {
            "id": g.id,
            "eps": g.eps,
            "paciente": g.paciente,
            "codigo_glosa": g.codigo_glosa,
            "valor_objetado": g.valor_objetado,
            "valor_aceptado": g.valor_aceptado,
            "etapa": g.etapa,
            "estado": g.estado,
            "dictamen": g.dictamen,
            "dias_restantes": g.dias_restantes,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
        }
        for g in glosas
    ]


@router.get("/historial-paginado")
def historial_paginado(
    page: int = 1,
    per_page: int = 20,
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Historial con paginación y filtros"""
    repo = GlosaRepository(db)
    resultado = repo.listar_paginado(page=page, per_page=per_page, eps=eps, estado=estado, search=search)
    
    return {
        "items": [
            {
                "id": g.id,
                "eps": g.eps,
                "paciente": g.paciente,
                "codigo_glosa": g.codigo_glosa,
                "valor_objetado": g.valor_objetado,
                "valor_aceptado": g.valor_aceptado,
                "etapa": g.etapa,
                "estado": g.estado,
                "dias_restantes": g.dias_restantes,
                "creado_en": g.creado_en.isoformat() if g.creado_en else None,
            }
            for g in resultado["items"]
        ],
        "total": resultado["total"],
        "page": resultado["page"],
        "per_page": resultado["per_page"],
        "pages": resultado["pages"],
    }


@router.get("/alertas")
def alertas(
    dias: int = 5,
    db:   Session       = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    alertas = repo.alertas_proximas(dias_limite=dias)
    return [
        {
            "id": a.id,
            "eps": a.eps,
            "paciente": a.paciente,
            "codigo_glosa": a.codigo_glosa,
            "valor_objetado": a.valor_objetado,
            "dias_restantes": a.dias_restantes,
            "estado": a.estado,
        }
        for a in alertas
    ]


@router.get("/metrics")
def metrics(
    db:   Session       = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.metrics()


@router.patch("/{glosa_id}/estado")
def actualizar_estado(
    glosa_id: int,
    nuevo_estado: str,
    db:    Session        = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosa = repo.actualizar_estado(glosa_id, nuevo_estado, responsable="sistema")
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    logger.info(f"Estado actualizado | glosa_id={glosa_id} | nuevo_estado={nuevo_estado}")
    return {"message": "Estado actualizado", "glosa": glosa}


@router.get("/{glosa_id}")
def obtener_glosa(
    glosa_id: int,
    db:    Session       = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    return {
        "id": glosa.id,
        "eps": glosa.eps,
        "paciente": glosa.paciente,
        "codigo_glosa": glosa.codigo_glosa,
        "valor_objetado": glosa.valor_objetado,
        "valor_aceptado": glosa.valor_aceptado,
        "etapa": glosa.etapa,
        "estado": glosa.estado,
        "dictamen": glosa.dictamen,
        "dias_restantes": glosa.dias_restantes,
        "creado_en": glosa.creado_en.isoformat() if glosa.creado_en else None,
    }
