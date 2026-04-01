from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from database import get_db
from models.db import UsuarioRecord
from core.config import get_settings

settings = oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_usuario_actual(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="token")),
    db: Session = Depends(get_db),
) -> UsuarioRecord:
    """
    Valida el JWT y retorna el usuario activo.
    El token hardcodeado HUS2026 fue eliminado — solo JWT válido.
    """
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
    return usuario

# Alias para inyección en rutas — más legible en las firmas
CurrentUser = Depends(get_usuario_actual)
DB          = Depends(get_db)
