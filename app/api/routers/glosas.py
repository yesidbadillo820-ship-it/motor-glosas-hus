import re
import json
import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import GlosaResult, GlosaInput
from app.models.db import UsuarioRecord, GlosaRecord
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.contrato_repository import ContratoRepository
from app.services.glosa_service import GlosaService
from app.services.pdf_service import PdfService
from app.core.config import get_settings
from app.domain.services.scoring import MotorScoring
from app.domain.entities.glosa import GlosaEntity

logger = logging.getLogger("motor_glosas_v2")

router = APIRouter(prefix="/glosas", tags=["glosas"])


def get_glosa_service() -> GlosaService:
    cfg = get_settings()
    return GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
    )


@router.post("/analizar", response_model=GlosaResult)
async def analizar(
    eps:               str            = Form(...),
    etapa:             str            = Form(...),
    fecha_radicacion:  Optional[str]  = Form(None),
    fecha_recepcion:   Optional[str]  = Form(None),
    valor_aceptado:    str            = Form("0"),
    tabla_excel:       str            = Form(...),
    archivos:          list[UploadFile] = File(None),
    db:      Session      = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
    service: GlosaService  = Depends(get_glosa_service),
):
    # 1. Validar input con Pydantic
    try:
        data = GlosaInput(
            eps=eps, etapa=etapa,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
            valor_aceptado=valor_aceptado,
            tabla_excel=tabla_excel,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 2. Extraer PDF si viene adjunto
    contexto_pdf = ""
    if archivos:
        pdf_svc = PdfService()
        for archivo in archivos:
            if archivo.filename:
                contenido = await archivo.read()
                contexto_pdf += await pdf_svc.extraer(contenido)

    # 3. Obtener contratos vigentes
    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()

    # 4. Ejecutar análisis (lógica de negocio en el service)
    resultado = await service.analizar(data, contexto_pdf, contratos)

    # 5. Persistir en base de datos (repository, no el service)
    glosa_repo = GlosaRepository(db)
    val_obj = float(re.sub(r"[^\d]", "", resultado.valor_objetado) or 0)
    val_ac  = float(re.sub(r"[^\d]", "", valor_aceptado) or 0)
    
    scoring = MotorScoring()
    entity = GlosaEntity(
        valor_objetado=val_obj,
        dias_restantes=resultado.dias_restantes,
    )
    score = scoring.calcular_score(entity)
    
    fecha_rad = None
    fecha_rec = None
    if data.fecha_radicacion:
        fecha_rad = datetime.strptime(str(data.fecha_radicacion), "%Y-%m-%d")
    if data.fecha_recepcion:
        fecha_rec = datetime.strptime(str(data.fecha_recepcion), "%Y-%m-%d")

    glosa_repo.crear(
        eps=eps,
        paciente=resultado.paciente,
        codigo_glosa=resultado.codigo_glosa,
        valor_objetado=val_obj,
        valor_aceptado=val_ac,
        etapa=etapa,
        estado="RADICADA",
        dictamen=resultado.dictamen,
        dias_restantes=resultado.dias_restantes,
        modelo_ia=resultado.modelo_ia,
        score=score,
        fecha_radicacion=fecha_rad,
        fecha_recepcion=fecha_rec,
    )
    
    logger.info(json.dumps({
        "event": "glosa_creada",
        "eps": eps,
        "score": score,
        "valor": val_obj,
        "timestamp": datetime.utcnow().isoformat(),
    }))

    return resultado


@router.get("/historial", response_model=list)
def historial(
    limit: int = 50,
    eps:   Optional[str] = None,
    db:    Session        = Depends(get_db),
    _:     UsuarioRecord  = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.listar(limit=limit, eps=eps)


@router.get("/alertas")
def alertas(
    dias: int = 5,
    db:   Session       = Depends(get_db),
    _:    UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.alertas_proximas(dias_limite=dias)


@router.post("/{glosa_id}/transicionar")
def transicionar_estado(
    glosa_id: int,
    nuevo_estado: str,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosa = repo.actualizar_estado(glosa_id, nuevo_estado, usuario.nombre)
    
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    
    logger.info(json.dumps({
        "event": "transicion_estado",
        "glosa_id": glosa_id,
        "estado_anterior": "DESCONOCIDO",
        "estado_nuevo": nuevo_estado,
        "responsable": usuario.nombre,
        "timestamp": datetime.utcnow().isoformat(),
    }))
    
    return {"id": glosa.id, "estado": glosa.estado, "score": glosa.score}


@router.get("/dashboard/estadisticas")
def dashboard_estadisticas(
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    from sqlalchemy import func
    
    total = db.query(func.count(GlosaRecord.id)).scalar() or 0
    por_estado = db.query(
        GlosaRecord.estado,
        func.count(GlosaRecord.id),
        func.sum(GlosaRecord.valor_objetado),
    ).group_by(GlosaRecord.estado).all()
    
    por_eps = db.query(
        GlosaRecord.eps,
        func.count(GlosaRecord.id),
        func.sum(GlosaRecord.valor_objetado),
    ).group_by(GlosaRecord.eps).order_by(func.sum(GlosaRecord.valor_objetado).desc()).limit(10).all()
    
    aging = db.query(
        func.case(
            (GlosaRecord.dias_restantes <= 0, "VENCIDA"),
            (GlosaRecord.dias_restantes <= 30, "0-30"),
            (GlosaRecord.dias_restantes <= 60, "30-60"),
            else_="60+",
        ).label("rango"),
        func.count(GlosaRecord.id),
    ).group_by("rango").all()
    
    return JSONResponse({
        "total_glosas": total,
        "por_estado": [{"estado": e, "cantidad": c, "valor": float(v or 0)} for e, c, v in por_estado],
        "por_eps": [{"eps": e, "cantidad": c, "valor": float(v or 0)} for e, c, v in por_eps],
        "aging": [{"rango": r, "cantidad": c} for r, c in aging],
    })


@router.get("/{glosa_id}")
def obtener_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosa = repo.obtener_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    return glosa
