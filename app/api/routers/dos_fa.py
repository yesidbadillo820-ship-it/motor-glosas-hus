"""2FA TOTP para cuentas con rol sensible.

Flujo:
  1. Usuario llama POST /2fa/setup → obtiene secret + QR + códigos de respaldo
  2. Escanea el QR en Google Authenticator / Authy / 1Password
  3. Llama POST /2fa/activar con el código de 6 dígitos → se activa
  4. En el login (si totp_activo=1) debe mandar el código junto con password
"""
import base64
import io
import secrets
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.db import UsuarioRecord
from app.api.deps import get_usuario_actual, get_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/2fa", tags=["2fa"])


class CodigoInput(BaseModel):
    codigo: str = Field(..., min_length=6, max_length=6)


@router.post("/setup")
def setup_2fa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Genera secreto TOTP (si no existe) + URI para QR. No activa aún."""
    import pyotp
    if current_user.totp_activo:
        raise HTTPException(400, "2FA ya está activo. Desactiva primero si quieres regenerar.")

    secret = current_user.totp_secret or pyotp.random_base32()
    current_user.totp_secret = secret
    db.commit()

    # URI estándar otpauth:// para Google Authenticator / Authy / 1Password
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=current_user.email,
        issuer_name="Motor Glosas HUS",
    )
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="2FA_SETUP",
        tabla="usuarios",
        registro_id=current_user.id,
    )
    return {
        "secret": secret,
        "uri": uri,
        "instrucciones": "Escanea el QR en tu app de autenticación y envía el código de 6 dígitos al endpoint /2fa/activar",
    }


@router.get("/qr")
def qr_2fa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve la imagen PNG del QR para el secret actual del usuario."""
    import pyotp
    import qrcode
    if not current_user.totp_secret:
        raise HTTPException(400, "Primero llama a /2fa/setup para generar secret")
    uri = pyotp.TOTP(current_user.totp_secret).provisioning_uri(
        name=current_user.email,
        issuer_name="Motor Glosas HUS",
    )
    img = qrcode.make(uri, box_size=8)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/activar")
def activar_2fa(
    data: CodigoInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Activa 2FA validando el primer código de la app de autenticación."""
    import pyotp
    if not current_user.totp_secret:
        raise HTTPException(400, "Primero llama a /2fa/setup")
    if current_user.totp_activo:
        raise HTTPException(400, "2FA ya activo")
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(data.codigo, valid_window=1):
        raise HTTPException(400, "Código inválido. Verifica la hora del dispositivo.")
    current_user.totp_activo = 1
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="2FA_ACTIVAR",
        tabla="usuarios",
        registro_id=current_user.id,
    )
    return {"message": "2FA activado correctamente"}


@router.post("/desactivar")
def desactivar_2fa(
    data: CodigoInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Desactiva 2FA (requiere código actual para evitar uso malicioso)."""
    import pyotp
    if not current_user.totp_activo:
        raise HTTPException(400, "2FA no está activo")
    totp = pyotp.TOTP(current_user.totp_secret or "")
    if not totp.verify(data.codigo, valid_window=1):
        raise HTTPException(400, "Código inválido")
    current_user.totp_activo = 0
    current_user.totp_secret = None
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="2FA_DESACTIVAR",
        tabla="usuarios",
        registro_id=current_user.id,
    )
    return {"message": "2FA desactivado"}


@router.get("/estado")
def estado_2fa(current_user: UsuarioRecord = Depends(get_usuario_actual)):
    """Estado 2FA del usuario actual."""
    return {
        "configurado": bool(current_user.totp_secret),
        "activo": bool(current_user.totp_activo),
        "obligatorio_rol": current_user.rol == "SUPER_ADMIN",
    }


@router.post("/admin/forzar-desactivar/{usuario_id}")
def admin_forzar_desactivar(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """SUPER_ADMIN puede desactivar 2FA de otro usuario si este perdió su dispositivo."""
    u = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    u.totp_activo = 0
    u.totp_secret = None
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="2FA_RESET_ADMIN",
        tabla="usuarios",
        registro_id=usuario_id,
        detalle=f"Admin reseteó 2FA de {u.email}",
    )
    return {"message": f"2FA desactivado para {u.email}"}
