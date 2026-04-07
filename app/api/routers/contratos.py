from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_usuario_actual, get_db, verificar_rol
from app.models.schemas import ContratoInput
from app.infrastructure.db.models import UsuarioRecord
from app.infrastructure.repositories.contrato_repository import ContratoRepository

router = APIRouter(prefix="/contratos", tags=["contratos"])


@router.get("/")
def listar_contratos(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    """Retorna todos los contratos registrados en el HUS."""
    repo = ContratoRepository(db)
    contratos = repo.listar_todos()
    return [{"eps": c.eps, "detalles": c.detalles, "version": c.version} for c in contratos]


@router.post("/")
def crear_contrato(
    data: ContratoInput,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(verificar_rol(["admin"]))
):
    """Crea un nuevo contrato (solo admin)."""
    repo = ContratoRepository(db)
    contrato = repo.crear(data.eps, data.detalles)
    return {"eps": contrato.eps, "detalles": contrato.detalles, "version": contrato.version}


@router.put("/{eps}")
def actualizar_contrato(
    eps: str,
    data: ContratoInput,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(verificar_rol(["admin", "auditor"]))
):
    """Actualiza un contrato existente (versionamiento automático)."""
    repo = ContratoRepository(db)
    contrato = repo.actualizar(eps, data.detalles)
    return {"eps": contrato.eps, "detalles": contrato.detalles, "version": contrato.version}


@router.get("/{eps}")
def obtener_contrato(
    eps: str,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    """Obtiene el contrato vigente de una EPS."""
    repo = ContratoRepository(db)
    contrato = repo.obtener(eps)
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"eps": contrato.eps, "detalles": contrato.detalles, "version": contrato.version}


@router.get("/{eps}/historial")
def historial_contrato(
    eps: str,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    """Obtiene el historial de versiones de un contrato."""
    repo = ContratoRepository(db)
    versiones = repo.historial_versiones(eps)
    return [
        {"eps": c.eps, "detalles": c.detalles, "version": c.version, "vigente": c.vigente}
        for c in versiones
    ]


@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(verificar_rol(["admin"]))
):
    """Elimina el contrato de una EPS (solo admin)."""
    repo = ContratoRepository(db)
    exito = repo.eliminar(eps)
    if not exito:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"message": f"Contrato con {eps} eliminado correctamente"}