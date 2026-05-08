from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Cliente
from app.schemas import ClienteIn, ClienteOut

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("", response_model=list[ClienteOut])
def listar(
    q: str | None = Query(None, description="Buscar por nombre o teléfono"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Cliente)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Cliente.nombre.ilike(like), Cliente.telefono.ilike(like)))
    return query.order_by(Cliente.nombre).limit(200).all()


@router.post("", response_model=ClienteOut, status_code=201)
def crear(payload: ClienteIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = Cliente(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{cid}", response_model=ClienteOut)
def actualizar(cid: int, payload: ClienteIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Cliente, cid)
    if not obj:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in payload.model_dump().items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{cid}", status_code=204)
def eliminar(cid: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = db.get(Cliente, cid)
    if not obj:
        raise HTTPException(404, "Cliente no encontrado")
    db.delete(obj)
    db.commit()
