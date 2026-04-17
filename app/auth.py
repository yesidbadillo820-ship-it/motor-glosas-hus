import bcrypt as _bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from sqlalchemy.orm import Session

from app.models.db import UsuarioRecord
from app.core.config import get_settings


def get_password_hash(password: str) -> str:
    return _bcrypt.hashpw(
        password.encode("utf-8"),
        _bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def authenticate_user(db: Session, email: str, password: str) -> Optional[UsuarioRecord]:
    user = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    cfg = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=cfg.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, cfg.secret_key, algorithm=cfg.algorithm)