from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional, Callable

from app.database import get_db
from app.models.db import UsuarioRecord, ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR
from app.core.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token", auto_error=False)


# ── La clave inicial deja de servir para todo ───────────────────────────
#
# 11-09-2026. Auditoría externa, comprobada uno por uno contra el código:
#
#   1. La contraseña inicial de cada gestor es **la parte de su correo antes
#      de la arroba** (`scripts/generar_excel_usuarios.py:136`).
#   2. La lista de los 29 usuarios, con esa regla escrita, vive en
#      `docs/usuarios_motor_glosas.xlsx` y está en el repositorio desde la
#      PR #303.
#   3. El motor **marcaba** al usuario con `must_change_password`, el login
#      lo devolvía y la pantalla lo mostraba… pero **nadie lo exigía**. Este
#      archivo ni siquiera lo mencionaba.
#
# Juntando las tres: quien supiera el correo de un gestor entraba como él y
# usaba la API entera sin cambiar nada. En un sistema con historias clínicas
# eso no es una deuda técnica, es una puerta abierta.
#
# Ahora, con la clave inicial sin cambiar, solo se puede hacer lo justo para
# cambiarla. Todo lo demás contesta **428 (hace falta una condición previa)**,
# que es el código correcto: no es que no tenga permiso, es que le falta un
# paso.
RUTAS_CON_CLAVE_TEMPORAL: frozenset[str] = frozenset(
    {
        "/auth/cambiar-password",  # lo único que de verdad hace falta
        "/auth/logout",  # poder salirse siempre
        "/usuarios/yo",  # la pantalla saluda por el nombre
        "/sistema/version",  # el aviso de «nueva versión»
        "/health",
    }
)


def _con_clave_temporal_solo_puede_cambiarla(
    usuario: UsuarioRecord, request: Optional[Request]
) -> None:
    """Corta el paso al que no ha cambiado su contraseña inicial.

    `request` puede faltar en llamadas internas y en pruebas viejas; en ese
    caso no se corta nada, porque no hay una ruta que juzgar. Lo que importa
    es que TODA petición HTTP pasa por acá con su `request`.
    """
    if not getattr(usuario, "must_change_password", 0):
        return
    if request is None:
        return
    if (request.url.path or "").rstrip("/") in RUTAS_CON_CLAVE_TEMPORAL:
        return
    raise HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail=(
            "Debe cambiar la contraseña inicial antes de usar el motor. "
            "La contraseña con la que entró es temporal."
        ),
    )


def get_usuario_actual(
    request: Request = None,  # type: ignore[assignment]
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UsuarioRecord:
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

    usuario = (
        db.query(UsuarioRecord)
        .filter(
            UsuarioRecord.email == email,
            UsuarioRecord.activo == 1,
        )
        .first()
    )
    if not usuario:
        raise credentials_exception
    _con_clave_temporal_solo_puede_cambiarla(usuario, request)
    return usuario


def require_rol(*roles: str) -> Callable:
    def checker(current_user: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
        if current_user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acción no permitida. Se requiere uno de los roles: {', '.join(roles)}",
            )
        return current_user

    return checker


def get_admin(current_user: UsuarioRecord = Depends(get_usuario_actual)) -> UsuarioRecord:
    if current_user.rol != ROL_SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol SUPER_ADMIN")
    return current_user


def get_coordinador_o_admin(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> UsuarioRecord:
    if current_user.rol not in (ROL_SUPER_ADMIN, ROL_COORDINADOR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol COORDINADOR o superior")
    return current_user


def get_auditor_o_superior(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> UsuarioRecord:
    if current_user.rol not in (ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Se requiere rol AUDITOR o superior")
    return current_user
