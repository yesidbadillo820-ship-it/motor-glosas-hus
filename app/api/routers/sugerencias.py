"""R369: feedback in-app — gestores reportan bugs, ideas, mejoras.

POST /sugerencias                — crear (cualquier usuario autenticado)
GET  /sugerencias/yo             — listar las propias
GET  /admin/sugerencias          — listar todas (admin) con filtros
PUT  /admin/sugerencias/{id}     — triagear (cambiar estado, nota)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_admin, get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import SugerenciaRecord, UsuarioRecord

router = APIRouter(tags=["sugerencias"])

TIPOS_VALIDOS = {"BUG", "IDEA", "MEJORA", "OTRO"}
ESTADOS_VALIDOS = {"ABIERTA", "EN_REVISION", "RESUELTA", "DESCARTADA"}


class SugerenciaIn(BaseModel):
    tipo: str = Field(..., description="BUG | IDEA | MEJORA | OTRO")
    titulo: str = Field(..., min_length=4, max_length=200)
    descripcion: str = Field(..., min_length=10)
    pagina: Optional[str] = None
    glosa_id: Optional[int] = None


class SugerenciaTriajeIn(BaseModel):
    estado: str = Field(..., description="ABIERTA|EN_REVISION|RESUELTA|DESCARTADA")
    nota_admin: Optional[str] = None


def _to_dict(s: SugerenciaRecord) -> dict:
    return {
        "id": s.id,
        "creado_en": s.creado_en.isoformat() if s.creado_en else None,
        "autor_email": s.autor_email,
        "autor_nombre": s.autor_nombre,
        "autor_rol": s.autor_rol,
        "tipo": s.tipo,
        "titulo": s.titulo,
        "descripcion": s.descripcion,
        "pagina": s.pagina,
        "glosa_id": s.glosa_id,
        "estado": s.estado,
        "resuelto_en": s.resuelto_en.isoformat() if s.resuelto_en else None,
        "resuelto_por": s.resuelto_por,
        "nota_admin": s.nota_admin,
    }


@router.post("/sugerencias", status_code=201)
def crear_sugerencia(
    body: SugerenciaIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Cualquier usuario autenticado puede reportar."""
    tipo = body.tipo.upper()
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(400, f"tipo debe ser uno de {sorted(TIPOS_VALIDOS)}")

    s = SugerenciaRecord(
        autor_email=current_user.email,
        autor_nombre=current_user.nombre,
        autor_rol=current_user.rol,
        tipo=tipo,
        titulo=body.titulo.strip(),
        descripcion=body.descripcion.strip(),
        pagina=(body.pagina or None),
        glosa_id=body.glosa_id,
        estado="ABIERTA",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _to_dict(s)


@router.get("/sugerencias/yo")
def listar_mis_sugerencias(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista las sugerencias del usuario actual (las suyas)."""
    rows = (
        db.query(SugerenciaRecord)
        .filter(SugerenciaRecord.autor_email == current_user.email)
        .order_by(SugerenciaRecord.creado_en.desc())
        .limit(int(limit))
        .all()
    )
    return {
        "total": len(rows),
        "items": [_to_dict(s) for s in rows],
    }


@router.get("/admin/sugerencias")
def admin_listar_sugerencias(
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Lista global con filtros opcionales por estado/tipo. Solo SUPER_ADMIN."""
    q = db.query(SugerenciaRecord)
    if estado:
        e = estado.upper()
        if e in ESTADOS_VALIDOS:
            q = q.filter(SugerenciaRecord.estado == e)
    if tipo:
        t = tipo.upper()
        if t in TIPOS_VALIDOS:
            q = q.filter(SugerenciaRecord.tipo == t)
    rows = (
        q.order_by(SugerenciaRecord.creado_en.desc())
        .limit(int(limit))
        .all()
    )

    # Resumen agregado para badges del UI
    total_abiertas = (
        db.query(SugerenciaRecord)
        .filter(SugerenciaRecord.estado == "ABIERTA")
        .count()
    )
    total_bugs = (
        db.query(SugerenciaRecord)
        .filter(SugerenciaRecord.tipo == "BUG")
        .filter(SugerenciaRecord.estado.in_(["ABIERTA", "EN_REVISION"]))
        .count()
    )

    return {
        "total": len(rows),
        "abiertas_global": total_abiertas,
        "bugs_pendientes": total_bugs,
        "items": [_to_dict(s) for s in rows],
    }


@router.put("/admin/sugerencias/{sugerencia_id}")
def admin_triagear_sugerencia(
    sugerencia_id: int,
    body: SugerenciaTriajeIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Cambia estado y/o agrega nota administrativa. Solo SUPER_ADMIN."""
    s = (
        db.query(SugerenciaRecord)
        .filter(SugerenciaRecord.id == sugerencia_id)
        .first()
    )
    if not s:
        raise HTTPException(404, "Sugerencia no encontrada")

    estado_nuevo = (body.estado or "").upper()
    if estado_nuevo not in ESTADOS_VALIDOS:
        raise HTTPException(
            400, f"estado debe ser uno de {sorted(ESTADOS_VALIDOS)}",
        )

    s.estado = estado_nuevo
    if body.nota_admin is not None:
        s.nota_admin = body.nota_admin
    if estado_nuevo in ("RESUELTA", "DESCARTADA"):
        s.resuelto_en = ahora_utc()
        s.resuelto_por = current_user.email
    else:
        s.resuelto_en = None
        s.resuelto_por = None

    db.commit()
    db.refresh(s)
    return _to_dict(s)
