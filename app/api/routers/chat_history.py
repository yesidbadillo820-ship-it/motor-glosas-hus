"""Historial persistente del Asistente Maestro.

Cada usuario tiene N conversaciones con M mensajes que se guardan en
BD. Permite volver a una sesion anterior y continuar el contexto sin
perder la informacion intermedia.
"""
from __future__ import annotations
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import ChatConversacionRecord, ChatMensajeRecord, UsuarioRecord


router = APIRouter(prefix="/chat-history", tags=["chat-history"])


class ConversacionInput(BaseModel):
    titulo: str | None = Field(None, max_length=200)


class MensajeInput(BaseModel):
    rol: str = Field(..., pattern="^(user|assistant|tool_use|tool_result)$")
    contenido: str
    metadata_json: dict | None = None


@router.get("/conversaciones")
def listar_conversaciones(
    archivadas: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    q = db.query(ChatConversacionRecord).filter(
        ChatConversacionRecord.usuario_email == current_user.email
    )
    if archivadas:
        q = q.filter(ChatConversacionRecord.archivado == 1)
    else:
        q = q.filter(ChatConversacionRecord.archivado == 0)
    rows = q.order_by(ChatConversacionRecord.ultimo_mensaje_en.desc()).limit(max(1, min(limit, 200))).all()
    return [
        {
            "id": c.id,
            "titulo": c.titulo or f"Conversacion #{c.id}",
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
            "ultimo_mensaje_en": c.ultimo_mensaje_en.isoformat() if c.ultimo_mensaje_en else None,
            "archivado": bool(c.archivado),
        }
        for c in rows
    ]


@router.post("/conversaciones")
def crear_conversacion(
    data: ConversacionInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = ChatConversacionRecord(
        usuario_email=current_user.email,
        titulo=(data.titulo or "")[:200] or None,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "titulo": c.titulo, "creado_en": c.creado_en.isoformat() if c.creado_en else None}


@router.get("/conversaciones/{conv_id}/mensajes")
def listar_mensajes(
    conv_id: int,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = db.query(ChatConversacionRecord).filter(
        ChatConversacionRecord.id == conv_id,
        ChatConversacionRecord.usuario_email == current_user.email,
    ).first()
    if not c:
        raise HTTPException(404, "Conversacion no encontrada")
    rows = (
        db.query(ChatMensajeRecord)
        .filter(ChatMensajeRecord.conversacion_id == conv_id)
        .order_by(ChatMensajeRecord.creado_en.asc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return {
        "conversacion": {"id": c.id, "titulo": c.titulo},
        "mensajes": [
            {
                "id": m.id,
                "rol": m.rol,
                "contenido": m.contenido,
                "metadata": json.loads(m.metadata_json) if m.metadata_json else None,
                "creado_en": m.creado_en.isoformat() if m.creado_en else None,
            }
            for m in rows
        ],
    }


@router.post("/conversaciones/{conv_id}/mensajes")
def agregar_mensaje(
    conv_id: int,
    data: MensajeInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = db.query(ChatConversacionRecord).filter(
        ChatConversacionRecord.id == conv_id,
        ChatConversacionRecord.usuario_email == current_user.email,
    ).first()
    if not c:
        raise HTTPException(404, "Conversacion no encontrada")
    m = ChatMensajeRecord(
        conversacion_id=conv_id,
        rol=data.rol,
        contenido=data.contenido[:50000],
        metadata_json=json.dumps(data.metadata_json, ensure_ascii=False) if data.metadata_json else None,
    )
    db.add(m)
    c.ultimo_mensaje_en = ahora_utc()
    # Auto-titulo a partir del primer mensaje del usuario
    if not c.titulo and data.rol == "user":
        c.titulo = data.contenido[:80]
    db.commit()
    db.refresh(m)
    return {
        "id": m.id,
        "conversacion_id": m.conversacion_id,
        "rol": m.rol,
        "creado_en": m.creado_en.isoformat() if m.creado_en else None,
    }


@router.delete("/conversaciones/{conv_id}")
def borrar_conversacion(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = db.query(ChatConversacionRecord).filter(
        ChatConversacionRecord.id == conv_id,
        ChatConversacionRecord.usuario_email == current_user.email,
    ).first()
    if not c:
        raise HTTPException(404, "No encontrada")
    # Borrar mensajes asociados
    db.query(ChatMensajeRecord).filter(ChatMensajeRecord.conversacion_id == conv_id).delete()
    db.delete(c)
    db.commit()
    return {"ok": True, "id": conv_id}


@router.post("/conversaciones/{conv_id}/archivar")
def archivar_conversacion(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    c = db.query(ChatConversacionRecord).filter(
        ChatConversacionRecord.id == conv_id,
        ChatConversacionRecord.usuario_email == current_user.email,
    ).first()
    if not c:
        raise HTTPException(404, "No encontrada")
    c.archivado = 1 if not c.archivado else 0
    db.commit()
    return {"ok": True, "id": conv_id, "archivado": bool(c.archivado)}
