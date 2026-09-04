"""API de la PRE-AUDITORÍA CONCURRENTE (V3, Pilar 2).

Una sola ruta que importa:

    POST /pre-auditoria/evaluar

El HIS del hospital manda la factura que está a punto de timbrar y recibe el
dictamen. Sincrónica, con techo de 10 segundos.

Dos puertas, como en el resto del sistema:

  · **EL HIS** (una máquina) entra con el token de agente por el header
    `X-Agente-Token`. No tiene sesión, no tiene rol y no puede hacer nada
    más que pedir evaluaciones.
  · **EL AUDITOR** (una persona) entra con su sesión normal, para probar una
    factura a mano o revisar el histórico.

Acá no hay lógica de negocio: se recibe, se valida y se responde. El motor
vive en `app/services/preauditoria_concurrente.py`.
"""

from __future__ import annotations

import json
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_auditor_o_superior, oauth2_scheme
from app.core.config import get_settings
from app.database import get_db
from app.models.db import PreAuditoriaEventoRecord, UsuarioRecord
from app.services import preauditoria_concurrente as motor
from app.services.preauditoria_contrato import PayloadFactura, RespuestaPreAuditoria

router = APIRouter(prefix="/pre-auditoria", tags=["pre-auditoria-concurrente"])


def quien_pregunta(
    x_agente_token: str = Header(default=""),
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> str:
    """Devuelve el actor: «his» para la máquina, el correo para la persona.

    El token de agente se compara con `compare_digest` —comparar cadenas con
    `==` deja medir el tiempo y adivinar el token carácter por carácter—. Si
    no está configurado, la puerta de la máquina simplemente no existe: un
    despliegue sin configurar no expone la pre-auditoría a internet.
    """
    esperado = get_settings().agente_lotes_token
    if x_agente_token:
        if not esperado:
            raise HTTPException(503, "Puerta del HIS deshabilitada (falta AGENTE_LOTES_TOKEN).")
        if not secrets.compare_digest(x_agente_token, esperado):
            raise HTTPException(401, "Token de agente inválido.")
        return "his"

    from app.api.deps import get_usuario_actual

    usuario: UsuarioRecord = get_usuario_actual(token=token, db=db)
    return usuario.email


@router.post("/evaluar", response_model=RespuestaPreAuditoria)
async def evaluar_factura(
    payload: PayloadFactura,
    db: Session = Depends(get_db),
    actor: str = Depends(quien_pregunta),
) -> RespuestaPreAuditoria:
    """Dictamina una factura ANTES de que el HIS la timbre.

    Responde siempre: aunque la IA esté caída o la base tenga un mal momento,
    el facturador recibe el dictamen de las reglas duras. Lo único que devuelve
    error es una factura que no se puede leer (422, de Pydantic).
    """
    return await motor.evaluar(db, payload, actor=actor)


# ── Consulta del libro (solo personas) ──────────────────────────────────
class EventoDTO(BaseModel):
    id: int
    creado_en: Optional[str] = None
    factura: str = ""
    eps: str = ""
    estado: str = ""
    recomendacion_accion: str = ""
    valor_en_riesgo: float = 0.0
    valor_factura: float = 0.0
    total_alertas: int = 0
    cruce_clinico_estado: str = ""
    modelo_utilizado: str = ""
    duracion_ms: int = 0
    actor: str = ""


class DetalleEventoDTO(EventoDTO):
    alertas: list[dict] = []


def _dto(e: PreAuditoriaEventoRecord) -> EventoDTO:
    return EventoDTO(
        id=e.id,
        creado_en=e.creado_en.isoformat() if e.creado_en else None,
        factura=e.factura or "",
        eps=e.eps or "",
        estado=e.estado or "",
        recomendacion_accion=e.recomendacion_accion or "",
        valor_en_riesgo=float(e.valor_en_riesgo or 0.0),
        valor_factura=float(e.valor_factura or 0.0),
        total_alertas=int(e.total_alertas or 0),
        cruce_clinico_estado=e.cruce_clinico_estado or "",
        modelo_utilizado=e.modelo_utilizado or "",
        duracion_ms=int(e.duracion_ms or 0),
        actor=e.actor or "",
    )


@router.get("/eventos", response_model=list[EventoDTO])
def listar_eventos(
    factura: str = Query(default="", max_length=50),
    estado: str = Query(default="", max_length=20),
    limite: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_auditor_o_superior),
) -> list[EventoDTO]:
    """Lo que se ha pre-auditado, de lo más nuevo a lo más viejo."""
    consulta = db.query(PreAuditoriaEventoRecord)
    if factura:
        consulta = consulta.filter(PreAuditoriaEventoRecord.factura == factura.strip())
    if estado:
        consulta = consulta.filter(PreAuditoriaEventoRecord.estado == estado.strip().upper())
    filas = consulta.order_by(PreAuditoriaEventoRecord.id.desc()).limit(limite).all()
    return [_dto(f) for f in filas]


@router.get("/eventos/{evento_id}", response_model=DetalleEventoDTO)
def ver_evento(
    evento_id: int,
    db: Session = Depends(get_db),
    _: UsuarioRecord = Depends(get_auditor_o_superior),
) -> DetalleEventoDTO:
    """Un evento con sus alertas, tal como se respondieron ese día."""
    fila = db.get(PreAuditoriaEventoRecord, evento_id)
    if fila is None:
        raise HTTPException(404, "Ese evento de pre-auditoría no existe.")
    try:
        alertas = json.loads(fila.alertas or "[]")
    except Exception:
        alertas = []
    return DetalleEventoDTO(**_dto(fila).model_dump(), alertas=alertas)
