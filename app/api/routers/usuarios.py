from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.db import UsuarioRecord
from app.auth import get_password_hash
from app.api.deps import get_usuario_actual

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


class UsuarioCreate(BaseModel):
    nombre: str
    email: str
    password: str


class PasswordChange(BaseModel):
    nueva_password: str


@router.get("/")
def listar_usuarios(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista todos los usuarios registrados."""
    usuarios = db.query(UsuarioRecord).order_by(UsuarioRecord.id).all()
    return [
        {"id": u.id, "nombre": u.nombre, "email": u.email}
        for u in usuarios
    ]


@router.post("/", status_code=201)
def crear_usuario(
    data: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea un nuevo usuario."""
    email = data.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email inválido")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 6 caracteres")
    if not data.nombre.strip():
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    
    existe = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if existe:
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
    
    usuario = UsuarioRecord(
        nombre=data.nombre.strip(),
        email=email,
        password_hash=get_password_hash(data.password),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "message": "Usuario creado exitosamente"
    }


@router.patch("/{usuario_id}/password")
def cambiar_password(
    usuario_id: int,
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Cambia la contraseña de un usuario."""
    if len(data.nueva_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 6 caracteres")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    usuario.password_hash = get_password_hash(data.nueva_password)
    db.commit()
    return {"message": "Contraseña actualizada exitosamente"}


@router.delete("/{usuario_id}")
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Elimina un usuario."""
    if usuario_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario mientras estás activo")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    db.delete(usuario)
    db.commit()
    return {"message": f"Usuario {usuario_id} eliminado"}
