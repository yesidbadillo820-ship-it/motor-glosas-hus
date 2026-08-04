"""Router de firma digital — R85 P1.

Endpoints:
  POST /firma/verificar  — verifica la integridad de un dictamen firmado.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_auditor_o_superior
from app.models.db import UsuarioRecord
from app.services.firma_digital import verificar_firma

router = APIRouter(prefix="/firma", tags=["firma"])


class VerificarFirmaRequest(BaseModel):
    hash: str
    firma: str
    firmante: str
    glosa_id: int
    timestamp: str
    alg: str


class VerificarFirmaResponse(BaseModel):
    valida: bool
    verificado_por: str


@router.post("/verificar", response_model=VerificarFirmaResponse)
def verificar_firma_dictamen(
    payload: VerificarFirmaRequest,
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """R85 P1: verifica la integridad y autenticidad de la firma de un dictamen.

    Recibe el hash SHA-256 y la firma HMAC-SHA256 generados por
    /glosas/{id}/firma-dictamen y confirma que no han sido alterados.

    No requiere el texto original del dictamen: la verificación opera
    puramente sobre hash + firma + secret_key del servidor.

    Returns:
        {"valida": bool, "verificado_por": <email del usuario autenticado>}
    """
    valida = verificar_firma(
        hash_hex=payload.hash,
        firma_b64=payload.firma,
    )
    return VerificarFirmaResponse(
        valida=valida,
        verificado_por=current_user.email,
    )
