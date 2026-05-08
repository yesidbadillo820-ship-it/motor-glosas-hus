from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, verify_password
from app.database import get_db
from app.models import Usuario
from app.schemas import LoginRequest, TokenResponse, UsuarioOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Usuario).filter(Usuario.email == payload.email.lower()).first()
    if not user or not user.activo or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña inválidos")
    token = create_access_token({"sub": user.email, "rol": user.rol})
    return TokenResponse(
        access_token=token, nombre=user.nombre, rol=user.rol, email=user.email
    )


@router.get("/me", response_model=UsuarioOut)
def me(user: Usuario = Depends(get_current_user)):
    return user
