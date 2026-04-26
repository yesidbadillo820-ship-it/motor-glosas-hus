"""Endpoints de firma digital (R85 P1).

Independiente de /glosas porque se puede firmar/verificar texto
arbitrario, no solo dictámenes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord

router = APIRouter(prefix="/firma", tags=["firma"])


class VerificarFirmaRequest(BaseModel):
    """Payload para verificar una firma previamente generada."""
    hash: str = Field(..., min_length=10, max_length=200)
    firma: str = Field(..., min_length=10, max_length=2000)
    firmante: str = Field(..., max_length=200)
    glosa_id: int = Field(..., ge=0)
    timestamp: str = Field(..., max_length=50)
    alg: str | None = None


@router.post("/verificar")
def verificar_firma_endpoint(
    data: VerificarFirmaRequest,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R85 P1: verifica si una firma es válida.

    Útil para:
      - Validar evidencias en disputas (¿el dictamen entregado es
        idéntico al firmado?)
      - Auditoría externa: el equipo legal puede pasar por aquí
        cualquier firma generada por R84 P1 para confirmar integridad

    Devuelve {valida: true|false, alg_usado: ...}.
    """
    from app.services.firma_digital import verificar_firma
    valida = verificar_firma(
        hash_esperado=data.hash,
        firma_base64=data.firma,
        firmante=data.firmante,
        glosa_id=data.glosa_id,
        timestamp=data.timestamp,
        alg=data.alg,
    )
    return {
        "valida": bool(valida),
        "alg_consultado": data.alg or "auto",
        "verificado_por": current_user.email,
    }
