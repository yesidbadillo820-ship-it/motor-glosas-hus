from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_usuario_actual, get_db
from app.models.schemas import ContratoInput
from app.infrastructure.db.models import UsuarioRecord
from app.infrastructure.repositories.contrato_repository import ContratoRepository

router = APIRouter(prefix="/contratos", tags=["contratos"])

@router.get("/", response_model=List[dict])
def listar_contratos(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    repo = ContratoRepository(db)
    contratos = repo.obtener_todos()
    return [{"eps": c.eps, "detalles": c.detalles, "version": c.version} for c in contratos]


@router.post("/")
def crear_contrato(
    data: ContratoInput,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    if usuario.rol not in ["admin", "auditor"]:
        raise HTTPException(status_code=403, detail="Sin permisos para crear contratos")
    
    repo = ContratoRepository(db)
    return repo.crear(data.eps, data.detalles)


@router.put("/{eps}")
def actualizar_contrato(
    eps: str,
    data: ContratoInput,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    if usuario.rol not in ["admin", "auditor"]:
        raise HTTPException(status_code=403, detail="Sin permisos para actualizar contratos")
    
    repo = ContratoRepository(db)
    return repo.crear_version(data.eps, data.detalles)


@router.get("/{eps}/historial")
def historial_contrato(
    eps: str,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual)
):
    repo = ContratoRepository(db)
    return repo.listar_historial(eps)


@router.delete("/{eps}")
def eliminar_contrato(
    eps: str,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual)
):
    if usuario.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo admin puede eliminar contratos")
    
    repo = ContratoRepository(db)
    contrato = repo.obtener(eps)
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    
    contrato.activo = False
    db.commit()
    return {"message": f"Contrato con {eps} desactivado correctamente"}
