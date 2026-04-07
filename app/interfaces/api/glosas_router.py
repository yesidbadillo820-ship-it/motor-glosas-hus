from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import GlosaResult, GlosaInput
from app.infrastructure.db.models import UsuarioRecord
from app.infrastructure.repositories import GlosaRepository, ContratoRepository
from app.infrastructure.external import IAService, PdfService
from app.application.use_cases.analizar_glosa import AnalizarGlosaUseCase
from app.application.use_cases.gestionar_glosa import GestionarGlosaUseCase
from app.core.config import get_settings

router = APIRouter(prefix="/glosas", tags=["glosas"])


def get_ia_service() -> IAService:
    cfg = get_settings()
    return IAService(groq_api_key=cfg.groq_api_key, anthropic_api_key=cfg.anthropic_api_key)


def get_pdf_service() -> PdfService:
    return PdfService()


def get_analizar_use_case(
    db: Session = Depends(get_db),
    ia_service: IAService = Depends(get_ia_service),
) -> AnalizarGlosaUseCase:
    glosa_repo = GlosaRepository(db)
    contrato_repo = ContratoRepository(db)
    return AnalizarGlosaUseCase(glosa_repo, contrato_repo, ia_service)


def get_gestionar_use_case(db: Session = Depends(get_db)) -> GestionarGlosaUseCase:
    glosa_repo = GlosaRepository(db)
    return GestionarGlosaUseCase(glosa_repo)


def tarea_pdf_async(pdf_content: bytes, glosa_id: int):
    import asyncio
    import logging
    
    logger = logging.getLogger("background_tasks")
    logger.info(f"Iniciando tarea asíncrona para glosa {glosa_id}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        pdf_svc = PdfService()
        contenido = loop.run_until_complete(pdf_svc.extraer(pdf_content))
        logger.info(f"PDF extraído para glosa {glosa_id}: {len(contenido)} caracteres")
    except Exception as e:
        logger.error(f"Error procesando PDF en background: {e}")
    finally:
        loop.close()


@router.post("/analizar", response_model=GlosaResult)
async def analizar(
    eps: str = Form(...),
    etapa: str = Form(...),
    fecha_radicacion: Optional[str] = Form(None),
    fecha_recepcion: Optional[str] = Form(None),
    valor_aceptado: str = Form("0"),
    tabla_excel: str = Form(...),
    archivos: Optional[list[UploadFile]] = File(None),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
    use_case: AnalizarGlosaUseCase = Depends(get_analizar_use_case),
):
    try:
        data = GlosaInput(
            eps=eps,
            etapa=etapa,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
            valor_aceptado=valor_aceptado,
            tabla_excel=tabla_excel,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    
    contexto_pdf = ""
    if archivos:
        pdf_svc = get_pdf_service()
        for archivo in archivos:
            if archivo and archivo.filename:
                contenido = await archivo.read()
                contexto_pdf += await pdf_svc.extraer(contenido)
                
                if background_tasks and len(contenido) > 1000000:
                    background_tasks.add_task(tarea_pdf_async, contenido, 0)
    
    resultado = await use_case.ejecutar(data, contexto_pdf, usuario.id)
    
    return resultado


@router.get("/historial")
def historial(
    limit: int = 50,
    eps: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosas = repo.listar(limit=limit, eps=eps, estado=estado)
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
            "dias_restantes": g.dias_restantes,
            "score": g.score,
            "prioridad": g.prioridad,
            "creado_en": g.creado_en.isoformat() if g.creado_en else None,
        }
        for g in glosas
    ]


@router.get("/alertas")
def alertas(
    dias: int = 5,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    glosas = repo.alertas_proximas(dias_limite=dias)
    return {
        "total": len(glosas),
        "glosas": [
            {
                "id": g.id,
                "eps": g.eps,
                "paciente": g.paciente,
                "dias_restantes": g.dias_restantes,
                "estado": g.estado,
                "valor_objetado": g.valor_objetado,
            }
            for g in glosas
        ],
    }


@router.get("/estadisticas")
def estadisticas(
    eps: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository(db)
    return repo.estadisticas(eps)


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
    return {
        "id": glosa.id,
        "eps": glosa.eps,
        "paciente": glosa.paciente,
        "factura": glosa.factura,
        "autorizacion": glosa.autorizacion,
        "codigo_glosa": glosa.codigo_glosa,
        "valor_objetado": glosa.valor_objetado,
        "valor_aceptado": glosa.valor_aceptado,
        "etapa": glosa.etapa,
        "estado": glosa.estado,
        "dictamen": glosa.dictamen,
        "dias_restantes": glosa.dias_restantes,
        "score": glosa.score,
        "prioridad": glosa.prioridad,
        "modelo_ia": glosa.modelo_ia,
        "responsable_id": glosa.responsable_id,
        "creado_en": glosa.creado_en.isoformat() if glosa.creado_en else None,
    }


@router.post("/{glosa_id}/cambiar-estado")
def cambiar_estado(
    glosa_id: int,
    nuevo_estado: str,
    observacion: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    use_case = get_gestionar_use_case(db)
    try:
        glosa = use_case.cambiar_estado(glosa_id, nuevo_estado, usuario.id, observacion)
        return {"mensaje": f"Estado cambiado a {nuevo_estado}", "glosa_id": glosa.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{glosa_id}/asignar")
def asignar_responsable(
    glosa_id: int,
    responsable_id: int,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    use_case = get_gestionar_use_case(db)
    glosa = use_case.asignar_responsable(glosa_id, responsable_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    return {"mensaje": "Responsable asignado", "glosa_id": glosa.id}


@router.get("/workflow/estados")
def estados_workflow():
    from app.domain.services import WorkflowEngine
    return {
        "estados": list(WorkflowEngine.TRANSICIONES.keys()),
        "transiciones": WorkflowEngine.TRANSICIONES,
    }