"""Notas privadas por glosa, una por gestor.

Cada gestor puede dejar notas asociadas a una glosa que solo el ve.
Diferente de comentarios (publicos). Util para recordatorios
personales del flujo de trabajo.

Endpoints:
    GET    /notas-privadas/{glosa_id}  - obtiene la nota del usuario
                                          para esa glosa (404 si no
                                          hay)
    PUT    /notas-privadas/{glosa_id}  - upsert de la nota
    DELETE /notas-privadas/{glosa_id}  - borra la nota
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import NotaPrivadaRecord, UsuarioRecord


router = APIRouter(prefix="/notas-privadas", tags=["notas-privadas"])


class NotaInput(BaseModel):
    contenido: str = Field(..., max_length=4000)


@router.get("/{glosa_id}")
def obtener_nota(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve la nota privada del usuario actual para la glosa, o
    404 si no existe."""
    n = db.query(NotaPrivadaRecord).filter(
        NotaPrivadaRecord.glosa_id == glosa_id,
        NotaPrivadaRecord.autor_email == current_user.email,
    ).first()
    if not n:
        raise HTTPException(404, "Sin nota")
    return {
        "id": n.id,
        "glosa_id": n.glosa_id,
        "contenido": n.contenido,
        "creado_en": n.creado_en.isoformat() if n.creado_en else None,
        "actualizado_en": n.actualizado_en.isoformat() if n.actualizado_en else None,
    }


@router.put("/{glosa_id}")
def upsert_nota(
    glosa_id: int,
    data: NotaInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Crea o actualiza la nota privada del usuario actual para la
    glosa. Si el contenido es vacio, borra la nota."""
    contenido = (data.contenido or "").strip()
    n = db.query(NotaPrivadaRecord).filter(
        NotaPrivadaRecord.glosa_id == glosa_id,
        NotaPrivadaRecord.autor_email == current_user.email,
    ).first()
    if not contenido:
        if n:
            db.delete(n)
            db.commit()
        return {"ok": True, "borrada": True}
    if n:
        n.contenido = contenido[:4000]
        n.actualizado_en = ahora_utc()
    else:
        n = NotaPrivadaRecord(
            glosa_id=glosa_id,
            autor_email=current_user.email,
            contenido=contenido[:4000],
        )
        db.add(n)
    db.commit()
    db.refresh(n)
    return {
        "ok": True,
        "id": n.id,
        "glosa_id": n.glosa_id,
        "contenido": n.contenido,
        "actualizado_en": n.actualizado_en.isoformat() if n.actualizado_en else None,
    }


@router.delete("/{glosa_id}")
def borrar_nota(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    n = db.query(NotaPrivadaRecord).filter(
        NotaPrivadaRecord.glosa_id == glosa_id,
        NotaPrivadaRecord.autor_email == current_user.email,
    ).first()
    if not n:
        raise HTTPException(404, "Sin nota para borrar")
    db.delete(n)
    db.commit()
    return {"ok": True, "borrada": True}


@router.get("")
def listar_mias(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista todas las notas privadas del usuario actual ordenadas por
    actualizado_en desc. Util para "mis recordatorios pendientes"."""
    rows = (
        db.query(NotaPrivadaRecord)
        .filter(NotaPrivadaRecord.autor_email == current_user.email)
        .order_by(NotaPrivadaRecord.actualizado_en.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": n.id,
            "glosa_id": n.glosa_id,
            "contenido": n.contenido,
            "actualizado_en": n.actualizado_en.isoformat() if n.actualizado_en else None,
        }
        for n in rows
    ]
