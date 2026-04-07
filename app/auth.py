from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.infrastructure.db.models import UsuarioRecord
from app.core.config import get_settings

# Configuración de hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara una contraseña en texto plano con su hash almacenado."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Genera un hash seguro a partir de una contraseña."""
    # Codificar a utf-8 previene errores comunes en ciertas versiones de passlib
    return pwd_context.hash(password.encode('utf-8'))

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
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=cfg.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    
    # Firmar el token usando la SECRET_KEY centralizada
    encoded_jwt = jwt.encode(
        to_encode, 
        cfg.secret_key, 
        algorithm=cfg.algorithm
    )
    
    return encoded_jwt
