"""Endpoint checklist pre-radicación."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.services.validador_dictamen import evaluar_dictamen

router = APIRouter(prefix="/validador", tags=["validador"])


class ValidarRequest(BaseModel):
    argumento: str = Field(..., description="HTML o texto del dictamen")
    codigo_glosa: str = Field("", description="Código de glosa (TA0801, FA0202...)")
    cups: Optional[str] = None
    valor_original: Optional[str] = Field(None, description="Valor objetado extraído del texto")
    codigo_respuesta: Optional[str] = Field(None, description="RE9502/RE9602/RE9901")
    eps: Optional[str] = ""


@router.post("/pre-radicacion")
def validar_pre_radicacion(
    req: ValidarRequest,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Corre el checklist de 10 puntos sobre el dictamen. Retorna score, veredicto y detalle."""
    resultado = evaluar_dictamen(
        argumento_html=req.argumento,
        codigo_glosa=req.codigo_glosa,
        cups_esperado=req.cups,
        valor_original=req.valor_original,
        codigo_respuesta=req.codigo_respuesta,
        eps=req.eps or "",
    )
    return resultado
