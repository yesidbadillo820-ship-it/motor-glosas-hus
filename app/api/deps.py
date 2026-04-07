from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from app.database import get_db
from app.infrastructure.db.models import UsuarioRecord
from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_usuario_actual(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioRecord:
    """
    Valida el JWT y retorna el usuario activo.
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
    if not usuario or not usuario.activo:
        raise credentials_exception
    return usuario


def verificar_rol(roles_permitidos: list[str]):
    def _verificar(usuario: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
        if usuario.rol not in roles_permitidos and usuario.rol != "admin":
            raise HTTPException(
                status_code=403,
                detail=f"Rol '{usuario.rol}' no tiene acceso a este recurso"
            )
        return usuario
    return _verificar


def verificar_eps(eps_permitidos: list[str]):
    def _verificar(
        usuario: UsuarioRecord = Depends(get_usuario_actual),
    ) -> UsuarioRecord:
        import json
        
        if usuario.rol == "admin":
            return usuario
        
        if not eps_permitidos:
            return usuario
        
        eps_permitidos_usuario = json.loads(usuario.eps_permitidos) if usuario.eps_permitidos else []
        
        for eps in eps_permitidos:
            if eps.upper() not in [e.upper() for e in eps_permitidos_usuario]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Usuario no tiene acceso a EPS: {eps}"
                )
        return usuario


CurrentUser = Depends(get_usuario_actual)
DB = Depends(get_db)