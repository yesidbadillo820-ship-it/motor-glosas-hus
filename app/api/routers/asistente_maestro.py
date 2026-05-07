"""
asistente_maestro.py — Endpoint del chat unificado con la IA mente maestra.

POST /asistente/chat
  Body: {mensajes: [{role, content}, ...]}
  Returns: {respuesta, tools_llamadas, modelo, tokens}

El usuario escribe lo que quiera en lenguaje natural y la IA decide
qué herramientas invocar (auditar, buscar, lookup norma, etc.).
"""
from __future__ import annotations
import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/asistente", tags=["asistente-maestro"])


class Mensaje(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    mensajes: list[Mensaje] = Field(..., min_length=1, max_length=20)


@router.post("/chat")
async def chat_asistente(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Chat con la mente maestra IA. Multi-turn — el frontend mantiene
    el historial y lo manda completo en cada llamada.

    La IA tiene acceso a 9 tools que cubren TODO el sistema:
      buscar_soportes, auditar_factura, buscar_glosa, lookup_norma,
      buscar_clausulas, lookup_tarifa, precedente_levantado, stats, ...

    Costo: $0.05-0.20 USD por turno según cuántas tools llame.
    """
    from app.services.asistente_maestro import chat_con_asistente

    mensajes_dict = [m.model_dump() for m in payload.mensajes]
    if not any(m["role"] == "user" for m in mensajes_dict):
        raise HTTPException(400, "Al menos un mensaje del usuario requerido")

    # Audit log: el chat puede invocar lectura de PHI (historias clínicas
    # vía auditar_factura). Registramos la consulta inicial.
    try:
        ultimo_user = next(m for m in reversed(mensajes_dict) if m["role"] == "user")
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="ASISTENTE_CHAT",
            tabla="asistente_maestro",
            detalle=ultimo_user["content"][:300],
            ip=request.client.host if request.client else None,
        )
    except Exception:
        pass

    resultado = await chat_con_asistente(
        mensajes=mensajes_dict,
        db=db,
        current_user=current_user,
    )

    if resultado.get("error"):
        raise HTTPException(500, resultado["error"])

    return resultado
