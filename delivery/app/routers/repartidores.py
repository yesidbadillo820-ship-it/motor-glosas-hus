from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Repartidor
from app.schemas import RepartidorIn, RepartidorOut

router = APIRouter(prefix="/api/repartidores", tags=["repartidores"])


@router.get("", response_model=list[RepartidorOut])
def listar(
    solo_activos: bool = False,
    solo_disponibles: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Repartidor)
    if solo_activos:
        query = query.filter(Repartidor.activo == 1)
    if solo_disponibles:
        query = query.filter(Repartidor.disponible == 1, Repartidor.activo == 1)
    return query.order_by(Repartidor.nombre).all()


@router.post("", response_model=RepartidorOut, status_code=201)
def crear(payload: RepartidorIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = Repartidor(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{rid}", response_model=RepartidorOut)
def actualizar(rid: int, payload: RepartidorIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Repartidor, rid)
    if not obj:
        raise HTTPException(404, "Repartidor no encontrado")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.post("/{rid}/disponibilidad", response_model=RepartidorOut)
def cambiar_disponibilidad(rid: int, disponible: bool, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Repartidor, rid)
    if not obj:
        raise HTTPException(404, "Repartidor no encontrado")
    obj.disponible = 1 if disponible else 0
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{rid}", status_code=204)
def eliminar(rid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Repartidor, rid)
    if not obj:
        raise HTTPException(404, "Repartidor no encontrado")
    db.delete(obj)
    db.commit()
