from fastapi import APIRouter, Depends, Form, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
from slowapi.util import get_remote_address

from app.core.logging_utils import logger
from app.database import get_db
from app.models.db import UsuarioRecord
from app.models.schemas import TokenResponse, CambiarPasswordRequest
from app.auth import authenticate_user, create_access_token, get_password_hash, verify_password
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.api.deps import get_usuario_actual, get_admin
from datetime import datetime as _dt

router = APIRouter(tags=["auth"])


@router.post("/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    totp: Optional[str] = Form(None),
    db: Session = Depends(get_db),
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
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)
    logger.info(f"[AUTH-OK] Login exitoso | email={user.email} | rol={user.rol} | ip={ip_cliente}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "nombre": user.nombre,
        "rol": user.rol,
        "must_change_password": bool(getattr(user, "must_change_password", 0)),
    }


_PASSWORDS_DEBILES = {
    "admin",
    "admin123",
    "password",
    "123456",
    "hus2026",
    "12345678",
    "qwerty",
    "abc123",
    "contraseña",
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


@router.post("/auth/logout")
def logout(
    request: Request,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R82 P2: marca el cierre de sesión del usuario en el audit log.

    Como los JWT son stateless, el endpoint no invalida el token
    activamente (eso requeriría un blocklist en Redis). El frontend
    debe DESCARTAR el token tras llamar /logout — esto solo registra
    la intención del usuario para auditoría regulatoria.

    Útil para:
      - Trazabilidad: "¿quién cerró sesión y a qué hora?"
      - Forense: si hay duda sobre actividad post-logout
      - Cumplimiento Habeas Data (Ley 1581/2012)
    """
    ip = get_remote_address(request)
    logger.info(f"[AUTH-LOGOUT] Cierre de sesión | email={current_user.email} | ip={ip}")
    return {
        "ok": True,
        "mensaje": "Sesión cerrada. Descarte el token en el cliente.",
    }


@router.post("/auth/token-integracion")
def emitir_token_integracion(
    request: Request,
    email: str = Form(...),
    dias: int = Form(365),
    admin: UsuarioRecord = Depends(get_admin),
    db: Session = Depends(get_db),
):
    """Emite un token JWT de LARGA DURACIÓN para una cuenta de servicio
    (jump-box de soportes, integraciones externas).

    Por qué existe: el token normal expira en 8h (access_token_expire_minutes
    = 480), lo cual rompe un agente 24/7 como tools/jumpbox_sync.py — moriría
    con 401 cada 8h y dejaría de sincronizar soportes. Este endpoint genera
    un token de hasta 730 días (2 años) que se pega en la variable
    MOTOR_TOKEN del jump-box.

    Seguridad:
      • Solo SUPER_ADMIN puede emitirlo.
      • El usuario destino debe existir, estar ACTIVO y tener rol AUDITOR o
        superior (el endpoint /soportes-auto/upload-bulk exige auditor+).
      • Se audita en log con email del admin que lo emitió.
      • Para revocar: desactivar la cuenta de servicio en el panel Usuarios
        (get_usuario_actual valida `activo` en cada request).
    """
    ip = get_remote_address(request)
    email_norm = (email or "").strip().lower()

    destino = db.query(UsuarioRecord).filter(UsuarioRecord.email == email_norm).first()
    if not destino:
        raise HTTPException(404, f"No existe usuario con email {email_norm!r}")
    if not destino.activo:
        raise HTTPException(400, "La cuenta de servicio está desactivada")
    if destino.rol not in ("SUPER_ADMIN", "COORDINADOR", "AUDITOR"):
        raise HTTPException(
            400,
            f"La cuenta debe tener rol AUDITOR o superior para subir soportes "
            f"(rol actual: {destino.rol}).",
        )

    # Límite duro de 2 años para no emitir tokens eternos.
    dias = max(1, min(int(dias or 365), 730))
    token = create_access_token(
        data={"sub": destino.email},
        expires_delta=timedelta(days=dias),
    )
    logger.warning(
        f"[AUTH-TOKEN-INTEGRACION] Token de {dias}d emitido por {admin.email} "
        f"para cuenta de servicio {destino.email} (rol={destino.rol}) | ip={ip}"
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": destino.email,
        "rol": destino.rol,
        "expira_en_dias": dias,
        "uso": (
            "Pega este token en la variable MOTOR_TOKEN del jump-box "
            "(tools/jumpbox_sync.py). Para revocarlo, desactiva la cuenta "
            "de servicio en el panel Usuarios."
        ),
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
        data={"sub": current_user.email},
        expires_delta=expires,
    )
    logger.info(f"[AUTH-REFRESH] Token renovado | email={current_user.email} | ip={ip}")
    return {
        "access_token": new_token,
        "token_type": "bearer",
        "nombre": current_user.nombre,
        "rol": current_user.rol,
        "must_change_password": bool(getattr(current_user, "must_change_password", 0)),
    }
