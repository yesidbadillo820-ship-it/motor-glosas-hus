from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Comercio
from app.schemas import ComercioIn, ComercioOut

router = APIRouter(prefix="/api/comercios", tags=["comercios"])


@router.get("", response_model=list[ComercioOut])
def listar(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Comercio).order_by(Comercio.nombre).all()


@router.post("", response_model=ComercioOut, status_code=201)
def crear(payload: ComercioIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = Comercio(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{cid}", response_model=ComercioOut)
def actualizar(cid: int, payload: ComercioIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Comercio, cid)
    if not obj:
        raise HTTPException(404, "Comercio no encontrado")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{cid}", status_code=204)
def eliminar(cid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Comercio, cid)
    if not obj:
        raise HTTPException(404, "Comercio no encontrado")
    db.delete(obj)
    db.commit()
