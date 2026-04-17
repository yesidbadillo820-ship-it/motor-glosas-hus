from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.db import UsuarioRecord, ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR, ROL_VIEWER
from app.auth import get_password_hash
from app.api.deps import get_usuario_actual, get_admin, get_coordinador_o_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


class UsuarioCreate(BaseModel):
    nombre: str
    email: str
    password: str


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    nueva_password: str


class RolChange(BaseModel):
    rol: str


ROLES_VALIDOS = {ROL_SUPER_ADMIN, ROL_COORDINADOR, ROL_AUDITOR, ROL_VIEWER}


@router.get("/")
def listar_usuarios(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista todos los usuarios registrados."""
    usuarios = db.query(UsuarioRecord).order_by(UsuarioRecord.id).all()
    return [
        {"id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "activo": u.activo}
        for u in usuarios
    ]


@router.get("/roles/disponibles")
def listar_roles_disponibles(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista los roles disponibles con descripción (requiere autenticación)."""
    return [
        {"rol": ROL_SUPER_ADMIN, "descripcion": "Todo: usuarios, configuración, eliminar"},
        {"rol": ROL_COORDINADOR, "descripcion": "Ver todo, aprobar, exportar"},
        {"rol": ROL_AUDITOR, "descripcion": "Crear/responder glosas propias"},
        {"rol": ROL_VIEWER, "descripcion": "Solo lectura"},
    ]


def _garantizar_al_menos_un_super_admin_activo(db: Session, excluir_id: int = None):
    """Verifica que exista al menos un SUPER_ADMIN activo distinto al excluido.

    Se llama antes de cambiar rol, desactivar o eliminar para no dejar la
    instancia sin administrador alguno.
    """
    q = db.query(UsuarioRecord).filter(
        UsuarioRecord.rol == ROL_SUPER_ADMIN,
        UsuarioRecord.activo == 1,
    )
    if excluir_id is not None:
        q = q.filter(UsuarioRecord.id != excluir_id)
    if q.count() == 0:
        raise HTTPException(
            status_code=400,
            detail="No se puede dejar el sistema sin SUPER_ADMIN activo. "
                   "Asigna este rol a otro usuario antes de proceder.",
        )


@router.post("/", status_code=201)
def crear_usuario(
    data: UsuarioCreate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea un nuevo usuario."""
    email = data.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email inválido")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 6 caracteres")
    if not data.nombre.strip():
        raise HTTPException(status_code=400, detail="El nombre es requerido")
    
    existe = db.query(UsuarioRecord).filter(UsuarioRecord.email == email).first()
    if existe:
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
    
    usuario = UsuarioRecord(
        nombre=data.nombre.strip(),
        email=email,
        password_hash=get_password_hash(data.password),
        rol=ROL_AUDITOR,
        activo=1,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="CREAR",
        tabla="usuarios",
        registro_id=usuario.id,
        detalle=f"Usuario creado: {email} con rol {ROL_AUDITOR}"
    )
    
    return {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "message": "Usuario creado exitosamente"
    }


@router.patch("/{usuario_id}")
def editar_usuario(
    usuario_id: int,
    data: UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Edita nombre y/o email de un usuario (solo SUPER_ADMIN).

    Al menos uno de los dos campos debe venir en el body. El email
    se normaliza a minúsculas y se valida unicidad.
    """
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    cambios = []
    if data.nombre is not None:
        nuevo_nombre = data.nombre.strip()
        if not nuevo_nombre:
            raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
        if nuevo_nombre != usuario.nombre:
            cambios.append(("nombre", usuario.nombre, nuevo_nombre))
            usuario.nombre = nuevo_nombre

    if data.email is not None:
        nuevo_email = data.email.strip().lower()
        if not nuevo_email or "@" not in nuevo_email:
            raise HTTPException(status_code=400, detail="Email inválido")
        if nuevo_email != usuario.email:
            ya_existe = db.query(UsuarioRecord).filter(
                UsuarioRecord.email == nuevo_email,
                UsuarioRecord.id != usuario_id,
            ).first()
            if ya_existe:
                raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")
            cambios.append(("email", usuario.email, nuevo_email))
            usuario.email = nuevo_email

    if not cambios:
        return {"message": "Sin cambios", "id": usuario.id, "nombre": usuario.nombre, "email": usuario.email}

    db.commit()
    db.refresh(usuario)

    for campo, anterior, nuevo in cambios:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="ACTUALIZAR",
            tabla="usuarios",
            registro_id=usuario_id,
            campo=campo,
            valor_anterior=anterior,
            valor_nuevo=nuevo,
            detalle=f"{campo.capitalize()} cambiado de '{anterior}' a '{nuevo}'",
        )

    return {
        "message": "Usuario actualizado",
        "id": usuario.id,
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol,
        "activo": usuario.activo,
    }


@router.patch("/{usuario_id}/password")
def cambiar_password(
    usuario_id: int,
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Cambia la contraseña de un usuario."""
    if len(data.nueva_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener mínimo 6 caracteres")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    anterior = usuario.password_hash[:20] + "..."
    usuario.password_hash = get_password_hash(data.nueva_password)
    db.commit()
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="usuarios",
        registro_id=usuario_id,
        campo="password",
        detalle=f"Contraseña cambiada para usuario {usuario.email}"
    )
    return {"message": "Contraseña actualizada exitosamente"}


@router.patch("/{usuario_id}/rol")
def cambiar_rol(
    usuario_id: int,
    data: RolChange,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Cambia el rol de un usuario (solo SUPER_ADMIN)."""
    nuevo_rol = data.rol.upper()
    if nuevo_rol not in ROLES_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Use: {', '.join(ROLES_VALIDOS)}")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    anterior = usuario.rol
    # Si estamos degradando a un SUPER_ADMIN, validar que quede al menos otro activo
    if anterior == ROL_SUPER_ADMIN and nuevo_rol != ROL_SUPER_ADMIN:
        _garantizar_al_menos_un_super_admin_activo(db, excluir_id=usuario_id)

    usuario.rol = nuevo_rol
    db.commit()

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="usuarios",
        registro_id=usuario_id,
        campo="rol",
        valor_anterior=anterior,
        valor_nuevo=nuevo_rol,
        detalle=f"Rol cambiado de {anterior} a {nuevo_rol} para {usuario.email}"
    )
    return {"message": "Rol actualizado", "nuevo_rol": nuevo_rol}


@router.patch("/{usuario_id}/activar")
def activar_desactivar(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Activa o desactiva un usuario."""
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    anterior = usuario.activo
    # Si se va a desactivar a un SUPER_ADMIN, validar que quede al menos otro activo
    if anterior == 1 and usuario.rol == ROL_SUPER_ADMIN:
        _garantizar_al_menos_un_super_admin_activo(db, excluir_id=usuario_id)

    usuario.activo = 0 if anterior == 1 else 1
    db.commit()
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ACTUALIZAR",
        tabla="usuarios",
        registro_id=usuario_id,
        campo="activo",
        valor_anterior=str(anterior),
        valor_nuevo=str(usuario.activo),
        detalle=f"Usuario {'activado' if usuario.activo else 'desactivado'}: {usuario.email}"
    )
    return {"message": f"Usuario {'activado' if usuario.activo else 'desactivado'}", "activo": usuario.activo}


@router.delete("/{usuario_id}")
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Elimina un usuario (solo SUPER_ADMIN)."""
    if usuario_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario mientras estás activo")

    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Si es el último SUPER_ADMIN activo, no permitir su eliminación
    if usuario.rol == ROL_SUPER_ADMIN and usuario.activo == 1:
        _garantizar_al_menos_un_super_admin_activo(db, excluir_id=usuario_id)

    email = usuario.email
    db.delete(usuario)
    db.commit()
    
    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="ELIMINAR",
        tabla="usuarios",
        registro_id=usuario_id,
        detalle=f"Usuario eliminado: {email}"
    )
    return {"message": f"Usuario {usuario_id} eliminado"}
