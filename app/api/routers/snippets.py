"""Snippets expandibles del usuario.

Cada gestor define atajos como '/ratif' -> texto fijo de 200 palabras.
Al escribir el atajo en cualquier textarea (con clase .snippet-enabled),
se expande automaticamente. Visibilidad PRIVADO / EQUIPO / GLOBAL.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import SnippetRecord, UsuarioRecord


router = APIRouter(prefix="/snippets", tags=["snippets"])


class SnippetInput(BaseModel):
    atajo: str = Field(..., min_length=1, max_length=50)
    contenido: str = Field(..., min_length=1, max_length=5000)
    descripcion: str | None = Field(None, max_length=200)
    visibilidad: str = "PRIVADO"


def _serializar(s: SnippetRecord) -> dict:
    return {
        "id": s.id,
        "usuario_email": s.usuario_email,
        "atajo": s.atajo,
        "contenido": s.contenido,
        "descripcion": s.descripcion,
        "visibilidad": s.visibilidad,
        "uso_count": s.uso_count or 0,
        "ultimo_uso": s.ultimo_uso.isoformat() if s.ultimo_uso else None,
        "creado_en": s.creado_en.isoformat() if s.creado_en else None,
    }


@router.get("")
def listar(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    rows = (
        db.query(SnippetRecord)
        .filter(
            (SnippetRecord.usuario_email == current_user.email)
            | (SnippetRecord.visibilidad == "GLOBAL")
        )
        .order_by(SnippetRecord.uso_count.desc(), SnippetRecord.creado_en.desc())
        .all()
    )
    return [_serializar(s) for s in rows]


@router.post("")
def crear(
    data: SnippetInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if data.visibilidad not in ("PRIVADO", "EQUIPO", "GLOBAL"):
        raise HTTPException(400, "visibilidad invalida")
    if data.visibilidad == "GLOBAL" and (current_user.rol or "").upper() not in ("COORDINADOR", "SUPER_ADMIN"):
        raise HTTPException(403, "Solo COORDINADOR/SUPER_ADMIN crea snippets GLOBAL")
    atajo = data.atajo.strip()
    if not atajo.startswith("/"):
        atajo = "/" + atajo
    # Validar unicidad por usuario
    existe = db.query(SnippetRecord).filter(
        SnippetRecord.usuario_email == current_user.email,
        SnippetRecord.atajo == atajo,
    ).first()
    if existe:
        raise HTTPException(400, f"Ya tenes un snippet con atajo {atajo}")
    s = SnippetRecord(
        usuario_email=current_user.email,
        atajo=atajo[:50],
        contenido=data.contenido[:5000],
        descripcion=(data.descripcion or "")[:200] or None,
        visibilidad=data.visibilidad,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serializar(s)


@router.put("/{snippet_id}")
def actualizar(
    snippet_id: int,
    data: SnippetInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    s = db.query(SnippetRecord).filter(SnippetRecord.id == snippet_id).first()
    if not s:
        raise HTTPException(404, "Snippet no encontrado")
    es_admin = (current_user.rol or "").upper() in ("COORDINADOR", "SUPER_ADMIN")
    if s.usuario_email != current_user.email and not es_admin:
        raise HTTPException(403, "Solo el dueno puede editar")
    if data.visibilidad == "GLOBAL" and not es_admin:
        raise HTTPException(403, "Solo COORDINADOR/SUPER_ADMIN crea GLOBAL")
    atajo = data.atajo.strip()
    if not atajo.startswith("/"):
        atajo = "/" + atajo
    s.atajo = atajo[:50]
    s.contenido = data.contenido[:5000]
    s.descripcion = (data.descripcion or "")[:200] or None
    s.visibilidad = data.visibilidad
    db.commit()
    return _serializar(s)


@router.delete("/{snippet_id}")
def borrar(
    snippet_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    s = db.query(SnippetRecord).filter(SnippetRecord.id == snippet_id).first()
    if not s:
        raise HTTPException(404, "Snippet no encontrado")
    es_admin = (current_user.rol or "").upper() in ("COORDINADOR", "SUPER_ADMIN")
    if s.usuario_email != current_user.email and not es_admin:
        raise HTTPException(403, "Solo el dueno puede borrar")
    db.delete(s)
    db.commit()
    return {"ok": True, "id": snippet_id}


@router.post("/{snippet_id}/usar")
def registrar_uso(
    snippet_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    s = db.query(SnippetRecord).filter(SnippetRecord.id == snippet_id).first()
    if not s:
        raise HTTPException(404, "Snippet no encontrado")
    s.uso_count = (s.uso_count or 0) + 1
    s.ultimo_uso = ahora_utc()
    db.commit()
    return {"ok": True, "uso_count": s.uso_count}
