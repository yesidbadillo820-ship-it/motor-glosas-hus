import re
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO

from app.application.use_cases.analisis_glosa import AnalisisGlosaUseCase
from app.application.use_cases.registro_glosa import RegistroGlosaUseCase
from app.application.use_cases.gestion_workflow import GestionWorkflowUseCase
from app.infrastructure.repositories.glosa_repository import GlosaRepository
from app.infrastructure.repositories.contrato_repository import ContratoRepository
from app.domain.services.scoring import SCORING_DEFAULT
from app.services.glosa_service import GlosaService
from app.services.pdf_service import PdfService as PDFService
from app.core.config import get_settings
from app.models.schemas import GlosaInput, GlosaResult
from app.api.deps import get_usuario_actual, get_db
from app.models.db import UsuarioRecord


router = APIRouter(prefix="/glosas", tags=["glosas"])


@router.post("/analizar", response_model=GlosaResult)
async def analizar(
    eps: str = Form(...),
    etapa: str = Form(...),
    fecha_radicacion: Optional[str] = Form(None),
    fecha_recepcion: Optional[str] = Form(None),
    valor_aceptado: str = Form("0"),
    tabla_excel: str = Form(...),
    archivos: list[UploadFile] = File(None),
    db=Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
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
        pdf_svc = PDFService()
        for archivo in archivos:
            if archivo.filename:
                contenido = await archivo.read()
                contexto_pdf += await pdf_svc.extraer(contenido)

    contrato_repo = ContratoRepository()
    contratos = contrato_repo.obtener_dict()

    use_case = AnalisisGlosaUseCase()
    resultado = await use_case.ejecutar(data, contexto_pdf, contratos)

    return resultado.resultado_ia


@router.post("/registrar")
def registrar_glosa(
    eps: str = Form(...),
    paciente: str = Form(...),
    codigo_glosa: str = Form(""),
    valor_objetado: float = Form(0),
    etapa: str = Form("INICIAL"),
    db=Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    from app.domain.entities.glosa import Glosa, Etapa, EstadoGlosa
    from app.domain.services.scoring import SCORING_DEFAULT

    glosa = Glosa(
        eps=eps.upper(),
        paciente=paciente,
        codigo_glosa=codigo_glosa or "PENDIENTE",
        valor_objetado=valor_objetado,
        etapa=Etapa(etapa.upper()),
        estado=EstadoGlosa.RADICADA,
    )

    repo = GlosaRepository()
    glosa_id = repo.guardar(glosa)

    return {"glosa_id": glosa_id, "eps": eps, "paciente": paciente}


@router.get("/historial")
def historial(
    limit: int = 50,
    eps: Optional[str] = None,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    if eps:
        return repo.listar_por_eps(eps, limit)
    return repo.listar_todos(limit)


@router.get("/alertas")
def alertas(
    dias: int = 5,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    vencidas = repo.listar_vencidas(dias)
    return [{"id": g.id, "eps": g.eps, "paciente": g.paciente, "dias_restantes": g.dias_restantes} for g in vencidas]


@router.get("/{glosa_id}")
def obtener_glosa(
    glosa_id: int,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    glosa = repo.buscar_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    return glosa


@router.get("/workflow/estados")
def obtener_estados():
    use_case = GestionWorkflowUseCase()
    return [e.value for e in use_case.obtener_estados()]


@router.get("/{glosa_id}/transiciones")
def obtener_transiciones(
    glosa_id: int,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    glosa = repo.buscar_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")

    use_case = GestionWorkflowUseCase()
    transiciones = use_case.obtener_transiciones(glosa.estado.value)
    return [{"desde": t.desde.value, "hacia": t.hacia.value, "accion": t.accion, "sla_dias": t.sla_dias} for t in transiciones]


@router.post("/{glosa_id}/cambiar_estado")
def cambiar_estado(
    glosa_id: int,
    nuevo_estado: str,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = GlosaRepository()
    glosa = repo.buscar_por_id(glosa_id)
    if not glosa:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")

    use_case = GestionWorkflowUseCase()
    resultado = use_case.cambiar_estado(
        glosa_id=glosa_id,
        estado_actual=glosa.estado.value,
        estado_nuevo=nuevo_estado,
        usuario_id=_.id,
    )

    if not resultado.valida:
        raise HTTPException(status_code=400, detail=resultado.mensaje)

    return {"mensaje": resultado.mensaje, "estado_anterior": resultado.estado_anterior, "estado_nuevo": resultado.estado_nuevo}