from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List

from app.api.deps import get_usuario_actual, get_db
from app.models.db import GlosaRecord, UsuarioRecord, ContratoVersionRecord, ReglaVersionRecord
from app.models.schemas import (
    UsuarioCreate, UsuarioResponse, TokenResponse, ContratoVersionInput, ContratoVersionResponse
)
from app.auth import get_password_hash, create_access_token, verificar_rol, verificar_permiso_eps
from app.core.observability import observability

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("/", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    usuario_data: UsuarioCreate,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    existente = db.query(UsuarioRecord).filter(UsuarioRecord.email == usuario_data.email).first()
    if existente:
        raise HTTPException(status_code=400, detail="Email ya registrado")
    
    nuevo = UsuarioRecord(
        nombre=usuario_data.nombre,
        email=usuario_data.email,
        password_hash=get_password_hash(usuario_data.password),
        rol=usuario_data.rol,
        eps_asignadas=",".join(usuario_data.eps_asignadas) if usuario_data.eps_asignadas else None,
        activo=True
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    
    observability.log_info(f"Usuario creado: {nuevo.email}", usuario_rol=nuevo.rol)
    
    return UsuarioResponse(
        id=nuevo.id,
        nombre=nuevo.nombre,
        email=nuevo.email,
        rol=nuevo.rol,
        eps_asignadas=usuario_data.eps_asignadas,
        activo=nuevo.activo
    )


@router.get("/me")
def obtener_usuario_actual(
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    eps_list = []
    if usuario.eps_asignadas:
        eps_list = [e.strip() for e in usuario.eps_asignadas.split(",")]
    
    return UsuarioResponse(
        id=usuario.id,
        nombre=usuario.nombre,
        email=usuario.email,
        rol=usuario.rol,
        eps_asignadas=eps_list,
        activo=usuario.activo
    )


@router.get("/", response_model=List[UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    if not verificar_rol(usuario, "admin"):
        raise HTTPException(status_code=403, detail="Solo administradores pueden listar usuarios")
    
    usuarios = db.query(UsuarioRecord).filter(UsuarioRecord.activo == True).all()
    
    resultado = []
    for u in usuarios:
        eps_list = []
        if u.eps_asignadas:
            eps_list = [e.strip() for e in u.eps_asignadas.split(",")]
        resultado.append(UsuarioResponse(
            id=u.id,
            nombre=u.nombre,
            email=u.email,
            rol=u.rol,
            eps_asignadas=eps_list,
            activo=u.activo
        ))
    
    return resultado


@router.put("/{usuario_id}")
def actualizar_usuario(
    usuario_id: int,
    nombre: Optional[str] = None,
    rol: Optional[str] = None,
    eps_asignadas: Optional[List[str]] = None,
    activo: Optional[bool] = None,
    db: Session = Depends(get_db),
    usuario_actual: UsuarioRecord = Depends(get_usuario_actual),
):
    if not verificar_rol(usuario_actual, "admin"):
        raise HTTPException(status_code=403, detail="Solo administradores pueden actualizar usuarios")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if nombre:
        usuario.nombre = nombre
    if rol:
        if rol not in ["admin", "auditor", "cartera"]:
            raise HTTPException(status_code=400, detail="Rol inválido")
        usuario.rol = rol
    if eps_asignadas is not None:
        usuario.eps_asignadas = ",".join(eps_asignadas) if eps_asignadas else None
    if activo is not None:
        usuario.activo = activo
    
    db.commit()
    
    observability.log_info(f"Usuario {usuario_id} actualizado", usuario_actual_id=usuario_actual.id)
    
    return {"success": True, "mensaje": "Usuario actualizado"}


@router.delete("/{usuario_id}")
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_usuario_actual),
    usuario_actual: UsuarioRecord = Depends(get_usuario_actual),
):
    if not verificar_rol(usuario_actual, "admin"):
        raise HTTPException(status_code=403, detail="Solo administradores pueden eliminar usuarios")
    
    usuario = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    usuario.activo = False
    db.commit()
    
    observability.log_info(f"Usuario {usuario_id} desactivado", usuario_actual_id=usuario_actual.id)
    
    return {"success": True, "mensaje": "Usuario desactivado"}


@router.post("/contratos-version", response_model=ContratoVersionResponse)
def crear_version_contrato(
    contrato: ContratoVersionInput,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    if not verificar_rol(usuario, "admin"):
        raise HTTPException(status_code=403, detail="Solo administradores pueden crear versiones")
    
    existente = db.query(ContratoVersionRecord).filter(
        ContratoVersionRecord.eps == contrato.eps.upper(),
        ContratoVersionRecord.version == contrato.version,
        ContratoVersionRecord.activo == True
    ).first()
    
    if existente:
        raise HTTPException(status_code=400, detail=f"Versión {contrato.version} ya existe para {contrato.eps}")
    
    nuevo = ContratoVersionRecord(
        eps=contrato.eps.upper(),
        version=contrato.version,
        detalles=contrato.detalles,
        activo=True
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    
    observability.log_info(f"Versión contrato {contrato.eps} v{contrato.version} creada")
    
    return ContratoVersionResponse(
        id=nuevo.id,
        eps=nuevo.eps,
        version=nuevo.version,
        detalles=nuevo.detalles,
        activo=nuevo.activo,
        creado_en=nuevo.creado_en.isoformat()
    )


@router.get("/contratos-version/{eps}")
def obtener_versiones_contrato(
    eps: str,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_usuario_actual),
):
    versiones = db.query(ContratoVersionRecord).filter(
        ContratoVersionRecord.eps == eps.upper(),
        ContratoVersionRecord.activo == True
    ).order_by(ContratoVersionRecord.version.desc()).all()
    
    return [
        {
            "id": v.id,
            "eps": v.eps,
            "version": v.version,
            "detalles": v.detalles,
            "creado_en": v.creado_en.isoformat()
        }
        for v in versiones
    ]


@router.get("/contratos-version")
def listar_todos_contratos_version(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    if not verificar_rol(usuario, "admin"):
        raise HTTPException(status_code=403, detail="Solo administradores pueden ver todas las versiones")
    
    versiones = db.query(ContratoVersionRecord).filter(
        ContratoVersionRecord.activo == True
    ).order_by(ContratoVersionRecord.eps, ContratoVersionRecord.version.desc()).all()
    
    return [
        {
            "id": v.id,
            "eps": v.eps,
            "version": v.version,
            "detalles": v.detalles,
            "creado_en": v.creado_en.isoformat()
        }
        for v in versiones
    ]