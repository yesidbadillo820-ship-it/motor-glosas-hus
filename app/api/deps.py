from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional, Callable

from app.database import get_db
from app.models.db import UsuarioRecord, ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR, ROL_VIEWER
from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


def get_usuario_actual(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioRecord:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
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

    usuario = db.query(UsuarioRecord).filter(
        UsuarioRecord.email == email,
        UsuarioRecord.activo == 1,
    ).first()
    if not usuario:
        raise credentials_exception
    return usuario


def require_rol(*roles: str) -> Callable:
    def checker(current_user: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
        if current_user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acción no permitida. Se requiere uno de los roles: {', '.join(roles)}",
            )
        return current_user
    return checker


def get_admin(current_user: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
    if current_user.rol != ROL_SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol SUPER_ADMIN")
    return current_user


def get_coordinador_o_admin(current_user: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
    if current_user.rol not in (ROL_SUPER_ADMIN, ROL_COORDINADOR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol COORDINADOR o superior")
    return current_user


def get_auditor_o_superior(current_user: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
    if current_user.rol not in (ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol AUDITOR o superior")
    return current_user
