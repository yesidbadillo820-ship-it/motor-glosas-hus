"""Presets de filtros guardados por usuario para Mis Glosas /
Historial. Permite que cada gestor reutilice con un click sus
combinaciones favoritas de filtros (EPS + estado + valor min/max +
orden, etc).

Endpoints:
    GET    /presets-filtros            - lista del usuario actual
    POST   /presets-filtros            - crea preset
    PUT    /presets-filtros/{id}       - actualiza preset
    DELETE /presets-filtros/{id}       - borra preset
    POST   /presets-filtros/{id}/usar  - registra uso (incrementa contador
                                         + actualiza ultimo_uso)
"""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import PresetFiltroRecord, UsuarioRecord


router = APIRouter(prefix="/presets-filtros", tags=["presets"])


class PresetInput(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=80)
    filtros: dict
    visibilidad: str = "PRIVADO"
    icono: str | None = None


def _serializar(p: PresetFiltroRecord) -> dict:
    try:
        filtros = json.loads(p.filtros) if p.filtros else {}
    except Exception:
        filtros = {}
    return {
        "id": p.id,
        "usuario_email": p.usuario_email,
        "nombre": p.nombre,
        "filtros": filtros,
        "visibilidad": p.visibilidad,
        "icono": p.icono,
        "creado_en": p.creado_en.isoformat() if p.creado_en else None,
        "ultimo_uso": p.ultimo_uso.isoformat() if p.ultimo_uso else None,
        "uso_count": p.uso_count or 0,
    }


@router.get("")
def listar_presets(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista los presets del usuario actual + los compartidos a su
    equipo + los GLOBAL."""
    rows = (
        db.query(PresetFiltroRecord)
        .filter(
            (PresetFiltroRecord.usuario_email == current_user.email)
            | (PresetFiltroRecord.visibilidad == "GLOBAL")
        )
        .order_by(PresetFiltroRecord.uso_count.desc(),
                  PresetFiltroRecord.creado_en.desc())
        .all()
    )
    return [_serializar(p) for p in rows]


@router.post("")
def crear_preset(
    data: PresetInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if data.visibilidad not in ("PRIVADO", "EQUIPO", "GLOBAL"):
        raise HTTPException(400, "visibilidad invalida")
    # Solo COORDINADOR/SUPER_ADMIN pueden crear GLOBAL
    if data.visibilidad == "GLOBAL" and (current_user.rol or "").upper() not in ("COORDINADOR", "SUPER_ADMIN"):
        raise HTTPException(403, "Solo COORDINADOR/SUPER_ADMIN puede crear presets GLOBAL")
    # Limite por usuario para evitar spam
    count = db.query(PresetFiltroRecord).filter(
        PresetFiltroRecord.usuario_email == current_user.email
    ).count()
    if count >= 30:
        raise HTTPException(400, "Maximo 30 presets por usuario")

    icono = (data.icono or "").strip()[:8]
    p = PresetFiltroRecord(
        usuario_email=current_user.email,
        nombre=data.nombre.strip()[:80],
        filtros=json.dumps(data.filtros, ensure_ascii=False),
        visibilidad=data.visibilidad,
        icono=icono or None,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _serializar(p)


@router.put("/{preset_id}")
def actualizar_preset(
    preset_id: int,
    data: PresetInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    p = db.query(PresetFiltroRecord).filter(PresetFiltroRecord.id == preset_id).first()
    if not p:
        raise HTTPException(404, "Preset no encontrado")
    # Solo el dueno o COORDINADOR/SUPER_ADMIN pueden editar
    es_admin = (current_user.rol or "").upper() in ("COORDINADOR", "SUPER_ADMIN")
    if p.usuario_email != current_user.email and not es_admin:
        raise HTTPException(403, "Solo el dueno del preset puede editarlo")
    if data.visibilidad not in ("PRIVADO", "EQUIPO", "GLOBAL"):
        raise HTTPException(400, "visibilidad invalida")
    if data.visibilidad == "GLOBAL" and not es_admin:
        raise HTTPException(403, "Solo COORDINADOR/SUPER_ADMIN puede crear presets GLOBAL")
    p.nombre = data.nombre.strip()[:80]
    p.filtros = json.dumps(data.filtros, ensure_ascii=False)
    p.visibilidad = data.visibilidad
    p.icono = (data.icono or "").strip()[:8] or None
    db.commit()
    return _serializar(p)


@router.delete("/{preset_id}")
def borrar_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    p = db.query(PresetFiltroRecord).filter(PresetFiltroRecord.id == preset_id).first()
    if not p:
        raise HTTPException(404, "Preset no encontrado")
    es_admin = (current_user.rol or "").upper() in ("COORDINADOR", "SUPER_ADMIN")
    if p.usuario_email != current_user.email and not es_admin:
        raise HTTPException(403, "Solo el dueno del preset puede borrarlo")
    db.delete(p)
    db.commit()
    return {"ok": True, "id": preset_id}


@router.post("/{preset_id}/usar")
def registrar_uso(
    preset_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Incrementa contador de uso y actualiza ultimo_uso. Util para
    ordenar presets por mas usados."""
    p = db.query(PresetFiltroRecord).filter(PresetFiltroRecord.id == preset_id).first()
    if not p:
        raise HTTPException(404, "Preset no encontrado")
    p.uso_count = (p.uso_count or 0) + 1
    p.ultimo_uso = ahora_utc()
    db.commit()
    return {"ok": True, "uso_count": p.uso_count}
