"""Comentarios threaded por seccion del dictamen.

Cada comentario asociado a un (glosa_id, seccion). Los hijos via
parent_id forman thread. Resuelto = oculta el thread del flujo
principal pero queda visible para revision.
"""
from __future__ import annotations
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import ComentarioThreadRecord, UsuarioRecord


router = APIRouter(prefix="/comentarios-thread", tags=["comentarios-thread"])


class ComentarioInput(BaseModel):
    glosa_id: int
    seccion: str = Field(..., max_length=50)
    contenido: str = Field(..., max_length=2000)
    parent_id: int | None = None


def _serializar(c: ComentarioThreadRecord) -> dict:
    return {
        "id": c.id,
        "glosa_id": c.glosa_id,
        "seccion": c.seccion,
        "parent_id": c.parent_id,
        "autor_email": c.autor_email,
        "autor_corto": (c.autor_email or "").split("@")[0],
        "contenido": c.contenido,
        "resuelto": bool(c.resuelto),
        "creado_en": c.creado_en.isoformat() if c.creado_en else None,
    }


@router.get("/glosa/{glosa_id}")
def listar_por_glosa(
    glosa_id: int,
    incluir_resueltos: bool = False,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve comentarios agrupados por seccion. Soporta threads
    anidados via parent_id."""
    q = db.query(ComentarioThreadRecord).filter(
        ComentarioThreadRecord.glosa_id == glosa_id
    )
    if not incluir_resueltos:
        q = q.filter(ComentarioThreadRecord.resuelto == 0)
    rows = q.order_by(ComentarioThreadRecord.creado_en.asc()).all()
    por_seccion = defaultdict(list)
    for r in rows:
        por_seccion[r.seccion].append(_serializar(r))
    return {
        "glosa_id": glosa_id,
        "secciones": dict(por_seccion),
        "total": len(rows),
    }


@router.post("")
def crear(
    data: ComentarioInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if not data.contenido.strip():
        raise HTTPException(400, "Contenido vacio")
    c = ComentarioThreadRecord(
        glosa_id=data.glosa_id,
        seccion=data.seccion[:50],
        parent_id=data.parent_id,
        autor_email=current_user.email,
        contenido=data.contenido[:2000],
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _serializar(c)


@router.post("/{comentario_id}/resolver")
def resolver(
    comentario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = db.query(ComentarioThreadRecord).filter(
        ComentarioThreadRecord.id == comentario_id
    ).first()
    if not c:
        raise HTTPException(404, "No encontrado")
    c.resuelto = 1 if not c.resuelto else 0
    db.commit()
    return {"ok": True, "id": comentario_id, "resuelto": bool(c.resuelto)}


@router.delete("/{comentario_id}")
def borrar(
    comentario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = db.query(ComentarioThreadRecord).filter(
        ComentarioThreadRecord.id == comentario_id
    ).first()
    if not c:
        raise HTTPException(404, "No encontrado")
    es_admin = (current_user.rol or "").upper() in ("COORDINADOR", "SUPER_ADMIN")
    if c.autor_email != current_user.email and not es_admin:
        raise HTTPException(403, "Solo el autor o admin puede borrar")
    db.delete(c)
    db.commit()
    return {"ok": True, "id": comentario_id}
