"""Chat del Asistente Maestro (multi-turn con tool calling).

El frontend hace POST /asistente/chat con {mensajes: [{role, content}]}
y espera {respuesta, tools_llamadas}. Delega en el servicio
chat_con_asistente que corre el loop de tools contra Anthropic.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.asistente_maestro import chat_con_asistente
from app.services.rate_limit_ia import consumir_cupo_ia as _consumir_cupo_ia

router = APIRouter(prefix="/asistente", tags=["asistente"])


class AsistenteChatIn(BaseModel):
    mensajes: list[dict] = Field(..., min_length=1, max_length=40)


@router.post("/chat")
async def asistente_chat(
    data: AsistenteChatIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
    _cupo_ia: None = Depends(_consumir_cupo_ia),
):
    mensajes = [
        m for m in data.mensajes
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    if not mensajes:
        raise HTTPException(400, "Sin mensajes válidos")

    cfg = get_settings()
    resultado = await chat_con_asistente(
        mensajes=mensajes,
        db=db,
        current_user=current_user,
        api_key=cfg.anthropic_api_key or None,
        modelo=cfg.anthropic_model or None,
    )

    if resultado.get("error"):
        raise HTTPException(502, resultado["error"])

    return {
        "respuesta": resultado.get("respuesta", ""),
        "tools_llamadas": resultado.get("tools_llamadas", []),
        "modelo": resultado.get("modelo"),
        "tokens": resultado.get("tokens"),
    }
