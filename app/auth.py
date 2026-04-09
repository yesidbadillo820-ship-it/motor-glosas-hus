from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.models.db import UsuarioRecord
from app.core.config import get_settings

# Configuración de hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara una contraseña en texto plano con su hash almacenado."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera un hash seguro a partir de una contraseña."""
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> Optional[UsuarioRecord]:
    """
    Busca al usuario en la base de datos y valida su contraseña.
    Retorna el objeto UsuarioRecord si es exitoso, de lo contrario None.
    """
    user = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crea un token JWT firmado para la sesión del usuario."""
    cfg = get_settings()
    to_encode = data.copy()

    # CORRECCIÓN: datetime.utcnow() está deprecated en Python 3.12+
    # Usar datetime.now(timezone.utc) en su lugar
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=cfg.access_token_expire_minutes)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        cfg.secret_key,
        algorithm=cfg.algorithm,
    )
    return encoded_jwt
