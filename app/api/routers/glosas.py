import re
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import GlosaResult, GlosaInput
from app.infrastructure.db.models import UsuarioRecord
from app.infrastructure.repositories.glosa_repository import GlosaRepository
from app.infrastructure.repositories.contrato_repository import ContratoRepository
from app.services.glosa_service import GlosaService
from app.services.pdf_service import PdfService
from app.core.config import get_settings
from app.application.use_cases import AnalisisGlosaUseCase
from app.infrastructure.external.observabilidad import observabilidad_logger

router = APIRouter(prefix="/glosas", tags=["glosas"])


def get_glosa_service() -> GlosaService:
    cfg = get_settings()
    return GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
    )


def generar_pdf_background(glosa_id: int, eps: str, paciente: str, dictamen: str):
    from app.services.pdf_service import PdfService
    import os
    
    pdf_service = PdfService()
    output_path = f"static/pdfs/glosa_{glosa_id}.pdf"
    
    try:
        pdf_service.generar(dictamen, eps, paciente, output_path)
        observabilidad_logger.info(
            f"PDF generado exitosamente",
            glosa_id=glosa_id,
            accion="pdf_generado"
        )
    except Exception as e:
        observabilidad_logger.error(
            f"Error generando PDF",
            glosa_id=glosa_id,
            error=e
        )


@router.post("/analizar", response_model=GlosaResult)
async def analizar(
    background_tasks: BackgroundTasks,
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
    start_time = time.time()
    
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

    contexto_pdf = ""
    if archivos:
        pdf_svc = PdfService()
        for archivo in archivos:
            if archivo.filename:
                contenido = await archivo.read()
                contexto_pdf += await pdf_svc.extraer(contenido)

    contrato_repo = ContratoRepository(db)
    contratos = contrato_repo.como_dict()

    resultado = await service.analizar(data, contexto_pdf, contratos)

    val_obj = float(re.sub(r"[^\d]", "", resultado.valor_objetado) or 0)
    val_ac  = float(re.sub(r"[^\d]", "", valor_aceptado) or 0)

    analisis_use_case = AnalisisGlosaUseCase()
    fecha_rad = datetime.strptime(fecha_radicacion, "%Y-%m-%d") if fecha_radicacion else None
    fecha_rec = datetime.strptime(fecha_recepcion, "%Y-%m-%d") if fecha_recepcion else None
    
    resultado_analisis = analisis_use_case.ejecutar(
        eps=eps,
        etapa=etapa,
        fecha_radicacion=fecha_rad,
        fecha_recepcion=fecha_rec,
        valor_aceptado=val_ac,
        tabla_excel=tabla_excel,
        contratos_db=contratos,
        contexto_pdf=contexto_pdf,
    )

    glosa_repo = GlosaRepository(db)
    glosa_db = glosa_repo.crear(
        eps=eps,
        paciente=resultado.paciente,
        codigo_glosa=resultado.codigo_glosa,
        valor_objetado=val_obj,
        valor_aceptado=val_ac,
        etapa=etapa,
        estado=resultado_analisis["glosa"].estado,
        dictamen=resultado.dictamen,
        dias_restantes=resultado.dias_restantes,
        dias_habiles=resultado_analisis["glosa"].dias_habiles,
        es_extemporanea=resultado_analisis["glosa"].es_extemporanea,
        score=resultado_analisis["scoring"].score,
        prioridad=resultado_analisis["scoring"].prioridad,
        modelo_ia=resultado.modelo_ia,
        responsable_id=usuario.id,
        fecha_radicacion=fecha_rad,
        fecha_recepcion=fecha_rec,
    )

    background_tasks.add_task(
        generar_pdf_background,
        glosa_db.id,
        eps,
        resultado.paciente,
        resultado.dictamen
    )

    duracion_ms = (time.time() - start_time) * 1000
    observabilidad_logger.log_analisis(
        glosa_db.id, eps, duracion_ms, True
    )

    return resultado


@router.get("/historial", response_model=list)
def historial(
    limit: int = 50,
    eps:   Optional[str] = None,
    estado: Optional[str] = None,
    prioridad: Optional[str] = None,
    db:    Session        = Depends(get_db),
    _:     UsuarioRecord  = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.listar(limit=limit, eps=eps, estado=estado, prioridad=prioridad)


@router.get("/alertas")
def alertas(
    dias: int = 5,
    db:   Session       = Depends(get_db),
    _:    UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.alertas_proximas(dias_limite=dias)


@router.get("/vencidas")
def vencidas(
    db:   Session       = Depends(get_db),
    _:    UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.listar_vencidas()


@router.get("/metrics")
def metrics(
    db:   Session       = Depends(get_db),
    _:    UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.metrics()


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
