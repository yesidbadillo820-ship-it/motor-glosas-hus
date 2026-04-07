from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from app.infrastructure.repositories.contrato_repository import ContratoRepository
from app.domain.entities.contrato import Contrato
from app.models.schemas import ContratoInput
from app.api.deps import get_usuario_actual, get_db
from app.models.db import UsuarioRecord


router = APIRouter(prefix="/contratos", tags=["contratos"])


@router.get("/")
def listar_contratos(
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = ContratoRepository()
    return repo.listar_todos()


@router.get("/{eps}")
def obtener_contrato(
    eps: str,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = ContratoRepository()
    contrato = repo.buscar_por_eps(eps)
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return contrato


@router.post("/")
def crear_contrato(
    input: ContratoInput,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = ContratoRepository()
    contrato = Contrato(eps=input.eps, detalles=input.detalles)
    exito = repo.guardar(contrato)
    if not exito:
        raise HTTPException(status_code=500, detail="Error guardando contrato")
    return {"eps": input.eps, "detalles": input.detalles}


@router.put("/{eps}")
def actualizar_contrato(
    eps: str,
    input: ContratoInput,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    repo = ContratoRepository()
    contrato = Contrato(eps=eps, detalles=input.detalles)
    exito = repo.guardar(contrato)
    if not exito:
        raise HTTPException(status_code=500, detail="Error actualizando contrato")
    return {"eps": input.eps, "detalles": input.detalles}


@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db=Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    exito = ContratoRepository().eliminar(eps)
    if not exito:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"mensaje": "Contrato eliminado"}