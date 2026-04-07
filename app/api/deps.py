from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from functools import wraps

from app.database import get_db
from app.infrastructure.db.models import UsuarioRecord
from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_usuario_actual(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioRecord:
    cfg = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, cfg.secret_key, algorithms=[cfg.algorithm])
        email: str = payload.get("sub")
        if not email:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if not usuario:
        raise credentials_exception
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
    return usuario


def requiere_rol(*roles: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            usuario = kwargs.get("usuario")
            if not usuario:
                for arg in args:
                    if isinstance(arg, UsuarioRecord):
                        usuario = arg
                        break
            
            if not usuario:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario no autenticado"
                )
            
            if usuario.rol not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Acceso denegado. Roles requeridos: {roles}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def verificar_permiso_eps(usuario: UsuarioRecord, eps: str) -> bool:
    if usuario.rol == "admin":
        return True
    
    eps_asignadas = usuario.eps_asignadas.split(",") if usuario.eps_asignadas else []
    return eps.upper() in [e.strip().upper() for e in eps_asignadas]


CurrentUser = Depends(get_usuario_actual)
DB = Depends(get_db)
