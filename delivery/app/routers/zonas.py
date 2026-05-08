from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Zona
from app.schemas import ZonaIn, ZonaOut

router = APIRouter(prefix="/api/zonas", tags=["zonas"])


@router.get("", response_model=list[ZonaOut])
def listar(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Zona).order_by(Zona.nombre).all()


@router.post("", response_model=ZonaOut, status_code=201)
def crear(payload: ZonaIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = Zona(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{zid}", response_model=ZonaOut)
def actualizar(zid: int, payload: ZonaIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Zona, zid)
    if not obj:
        raise HTTPException(404, "Zona no encontrada")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{zid}", status_code=204)
def eliminar(zid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Zona, zid)
    if not obj:
        raise HTTPException(404, "Zona no encontrada")
    db.delete(obj)
    db.commit()
