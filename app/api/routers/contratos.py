from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.schemas import ContratoInput
from app.repositories.contrato_repository import ContratoRepository
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/contratos", tags=["contratos"])

@router.get("/", response_model=List[dict])
def listar_contratos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Retorna todos los contratos registrados en el HUS."""
    repo = ContratoRepository(db)
    contratos = repo.listar()
    return [{"eps": c.eps, "detalles": c.detalles} for c in contratos]

@router.post("/upsert")
def crear_o_actualizar_contrato(
    data: ContratoInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea un nuevo contrato o actualiza uno existente si la EPS ya existe."""
    repo = ContratoRepository(db)
    return repo.upsert(data)

@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Elimina el contrato de una EPS específica."""
    repo = ContratoRepository(db)
    exito = repo.eliminar(eps)
    if not exito:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return {"message": f"Contrato con {eps} eliminado correctamente"}
