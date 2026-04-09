from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
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
    db: Session = Depends(get_db)
):
    cfg = get_settings()
    # Necesitas implementar authenticate_user en tu archivo auth.py
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=cfg.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "nombre": user.nombre
    }
