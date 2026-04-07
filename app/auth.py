from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.db import UsuarioRecord
from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLES_PERMITIDOS = ["admin", "auditor", "cartera"]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password.encode('utf-8'))


def authenticate_user(db: Session, email: str, password: str) -> Optional[UsuarioRecord]:
    user = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.activo:
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    cfg = get_settings()
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=cfg.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        cfg.secret_key, 
        algorithm=cfg.algorithm
    )
    
    return encoded_jwt


def verificar_rol(usuario: UsuarioRecord, rol_requerido: str) -> bool:
    """Verifica si el usuario tiene el rol requerido"""
    if rol_requerido == "admin":
        return usuario.rol == "admin"
    elif rol_requerido == "auditor":
        return usuario.rol in ["admin", "auditor"]
    elif rol_requerido == "cartera":
        return usuario.rol in ["admin", "cartera"]
    return False


def verificar_permiso_eps(usuario: UsuarioRecord, eps: str) -> bool:
    """Verifica si el usuario tiene acceso a la EPS"""
    if usuario.rol == "admin":
        return True
    
    if usuario.eps_asignadas:
        eps_asignadas = [e.strip().upper() for e in usuario.eps_asignadas.split(",")]
        return eps.upper() in eps_asignadas
    
    return False


def requiere_rol(rol_requerido: str):
    """Decorador para verificar rol en endpoints"""
    from functools import wraps
    from fastapi import HTTPException, status
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            usuario = kwargs.get("usuario")
            if not usuario:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no autenticado"
                )
            if not verificar_rol(usuario, rol_requerido):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Rol '{rol_requerido}' requerido"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator
