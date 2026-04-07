import re
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import GlosaResult, GlosaInput
from app.models.db import UsuarioRecord
from app.repositories.glosa_repository import GlosaRepository
from app.repositories.contrato_repository import ContratoRepository
from app.services.glosa_service import GlosaService
from app.services.pdf_service import PdfService
from app.core.config import get_settings

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

    glosa_repo.crear(
        eps=eps,
        paciente=resultado.paciente,
        codigo_glosa=resultado.codigo_glosa,
        valor_objetado=val_obj,
        valor_aceptado=val_ac,
        etapa=etapa,
        estado="ACEPTADA" if val_ac > 0 else "LEVANTADA",
        dictamen=resultado.dictamen,
        dias_restantes=resultado.dias_restantes,
        modelo_ia=resultado.modelo_ia,
    )

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
