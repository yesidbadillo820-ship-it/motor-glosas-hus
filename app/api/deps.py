from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional

from app.database import get_db
from app.models.db import UsuarioRecord
from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


def get_usuario_actual(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioRecord:
    """
    Valida el JWT y retorna el usuario activo.
    NOTA: El token hardcodeado HUS2026 fue ELIMINADO por ser un riesgo de seguridad crítico.
    """
    # ELIMINADO: token especial HUS2026 — era un backdoor de seguridad

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

    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if not usuario:
        raise credentials_exception
    return usuario


# Alias para inyección en rutas
CurrentUser = Depends(get_usuario_actual)
DB          = Depends(get_db)
