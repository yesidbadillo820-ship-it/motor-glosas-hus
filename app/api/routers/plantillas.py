from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.repositories.plantilla_repository import PlantillaRepository

router = APIRouter(prefix="/plantillas", tags=["plantillas"])

class PlantillaCreate(BaseModel):
    nombre: str
    codigo: Optional[str] = None
    tipo: Optional[str] = None
    eps: Optional[str] = None
    plantilla: str

class PlantillaUpdate(BaseModel):
    nombre: Optional[str] = None
    plantilla: Optional[str] = None
    activa: Optional[int] = None

@router.get("/")
def listar_plantillas(
    activa_only: bool = True,
    db: Session = Depends(get_db),
):
    """Lista todas las plantillas disponibles"""
    repo = PlantillaRepository(db)
    plantillas = repo.listar(activa_only=activa_only)
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "codigo": p.codigo,
            "tipo": p.tipo,
            "eps": p.eps,
            "plantilla": p.plantilla,
            "activa": p.activa,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in plantillas
    ]

@router.post("/")
def crear_plantilla(
    data: PlantillaCreate,
    db: Session = Depends(get_db),
):
    """Crea una nueva plantilla"""
    repo = PlantillaRepository(db)
    plantilla = repo.crear(
        nombre=data.nombre,
        codigo=data.codigo,
        tipo=data.tipo,
        eps=data.eps,
        plantilla=data.plantilla,
    )
    return {"id": plantilla.id, "message": "Plantilla creada"}

@router.get("/{plantilla_id}")
def obtener_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db),
):
    """Obtiene una plantilla por ID"""
    repo = PlantillaRepository(db)
    plantilla = repo.obtener_por_id(plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {
        "id": plantilla.id,
        "nombre": plantilla.nombre,
        "codigo": plantilla.codigo,
        "tipo": plantilla.tipo,
        "eps": plantilla.eps,
        "plantilla": plantilla.plantilla,
        "activa": plantilla.activa,
    }

@router.patch("/{plantilla_id}")
def actualizar_plantilla(
    plantilla_id: int,
    data: PlantillaUpdate,
    db: Session = Depends(get_db),
):
    """Actualiza una plantilla"""
    repo = PlantillaRepository(db)
    plantilla = repo.actualizar(
        plantilla_id,
        nombre=data.nombre,
        plantilla=data.plantilla,
        activa=data.activa,
    )
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"message": "Plantilla actualizada"}

@router.delete("/{plantilla_id}")
def eliminar_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db),
):
    """Elimina (desactiva) una plantilla"""
    repo = PlantillaRepository(db)
    resultado = repo.eliminar(plantilla_id)
    if not resultado:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"message": "Plantilla eliminada"}
