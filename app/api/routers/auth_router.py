from fastapi import APIRouter, Depends, Form, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.logging_utils import logger
from app.database import get_db
from app.models.db import UsuarioRecord
from app.models.schemas import TokenResponse, CambiarPasswordRequest
from app.auth import authenticate_user, create_access_token, get_password_hash, verify_password
from app.core.config import get_settings
from app.api.deps import get_usuario_actual
from datetime import datetime as _dt

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
    # IP del cliente para auditoría de seguridad. Se loguea en TODOS los
    # outcomes (éxito, password incorrecto, 2FA fallido) para detectar
    # patrones de brute-force en logs centralizados / Sentry.
    ip_cliente = get_remote_address(request)
    email_intento = (form_data.username or "").strip().lower()

    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logger.warning(
            f"[AUTH-FAIL] Intento de login con credenciales inválidas | "
            f"email={email_intento!r} | ip={ip_cliente}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2FA TOTP: si el usuario tiene activo el 2FA, exigir código válido
    if user.totp_activo and user.totp_secret:
        if not totp:
            logger.info(
                f"[AUTH-2FA] Solicitud 2FA pendiente | email={user.email} | ip={ip_cliente}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA requerido: envía el campo 'totp' con el código de 6 dígitos",
                headers={"X-2FA-Required": "true"},
            )
        import pyotp
        if not pyotp.TOTP(user.totp_secret).verify(totp.strip(), valid_window=1):
            logger.warning(
                f"[AUTH-2FA-FAIL] Código 2FA inválido | email={user.email} | ip={ip_cliente}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código 2FA inválido. Verifica la hora de tu dispositivo.",
            )

    access_token_expires = timedelta(minutes=cfg.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    logger.info(
        f"[AUTH-OK] Login exitoso | email={user.email} | rol={user.rol} | ip={ip_cliente}"
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "nombre": user.nombre,
        "rol": user.rol,
        "must_change_password": bool(getattr(user, "must_change_password", 0)),
    }


_PASSWORDS_DEBILES = {
    "admin", "admin123", "password", "123456", "hus2026",
    "12345678", "qwerty", "abc123", "contraseña",
}


def _validar_password_fuerte(password: str) -> Optional[str]:
    """Retorna un mensaje de error si el password es débil, o None si es válido."""
    if len(password) < 8:
        return "El password debe tener al menos 8 caracteres"
    if password.lower() in _PASSWORDS_DEBILES:
        return "El password es demasiado común. Usa uno más complejo"
    # Requisitos mínimos: al menos 1 letra + 1 número
    tiene_letra = any(c.isalpha() for c in password)
    tiene_digito = any(c.isdigit() for c in password)
    if not (tiene_letra and tiene_digito):
        return "El password debe contener al menos 1 letra y 1 número"
    return None


@router.post("/auth/cambiar-password")
@limiter.limit("10/minute")
async def cambiar_password(
    request: Request,
    payload: CambiarPasswordRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Cambia la contraseña del usuario autenticado.

    Requiere:
      - password_actual: la contraseña vigente (para verificación)
      - password_nueva: la nueva (mínimo 8 chars, con letra + número)
      - password_nueva_confirmacion: debe coincidir con password_nueva

    Tras el cambio limpia el flag must_change_password y registra la fecha.
    """
    # Validación: confirmación coincide
    if payload.password_nueva != payload.password_nueva_confirmacion:
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña y su confirmación no coinciden",
        )
    # Validación: no reutilizar el mismo password
    if payload.password_actual == payload.password_nueva:
        raise HTTPException(
            status_code=400,
            detail="La nueva contraseña debe ser diferente a la actual",
        )
    # Validación: password actual correcto
    if not verify_password(payload.password_actual, current_user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="La contraseña actual es incorrecta",
        )
    # Validación: fortaleza
    error = _validar_password_fuerte(payload.password_nueva)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Aplicar cambio
    current_user.password_hash = get_password_hash(payload.password_nueva)
    current_user.must_change_password = 0
    current_user.password_changed_at = _dt.utcnow()
    db.commit()
    return {
        "ok": True,
        "mensaje": "Contraseña actualizada correctamente",
    }


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_token(
    request: Request,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R82 P1: emite un nuevo token a un usuario ya autenticado.

    Extiende la sesión sin requerir credenciales (la UI lo llama
    automáticamente cuando detecta que el token expira pronto).

    Auditado en log para detectar refresh sospechosos (ej. el mismo
    usuario refrescando 100x en 1 min sería raro).

    Solo válido para usuarios ACTIVOS (si el admin desactivó la
    cuenta, no debe poder refrescar).
    """
    if not current_user.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario desactivado",
        )
    cfg = get_settings()
    ip = get_remote_address(request)
    expires = timedelta(minutes=cfg.access_token_expire_minutes)
    new_token = create_access_token(
        data={"sub": current_user.email}, expires_delta=expires,
    )
    logger.info(
        f"[AUTH-REFRESH] Token renovado | email={current_user.email} | ip={ip}"
    )
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "nombre": current_user.nombre,
        "rol": current_user.rol,
        "must_change_password": bool(getattr(current_user, "must_change_password", 0)),
    }
