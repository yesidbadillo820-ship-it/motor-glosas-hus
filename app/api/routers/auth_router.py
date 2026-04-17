from fastapi import APIRouter, Depends, Form, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.db import UsuarioRecord
from app.models.schemas import TokenResponse
from app.auth import authenticate_user, create_access_token
from app.core.config import get_settings

router = APIRouter(tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    totp: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    cfg = get_settings()
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2FA TOTP: si el usuario tiene activo el 2FA, exigir código válido
    if user.totp_activo and user.totp_secret:
        if not totp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA requerido: envía el campo 'totp' con el código de 6 dígitos",
                headers={"X-2FA-Required": "true"},
            )
        import pyotp
        if not pyotp.TOTP(user.totp_secret).verify(totp.strip(), valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código 2FA inválido. Verifica la hora de tu dispositivo.",
            )

    access_token_expires = timedelta(minutes=cfg.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "nombre": user.nombre,
        "rol": user.rol,
    }
