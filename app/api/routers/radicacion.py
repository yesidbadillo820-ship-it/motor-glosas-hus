"""Despacho de la radicación autónoma en portales (V3, Pilar 1).

Dos públicos, dos puertas:

  · EL AUDITOR (sesión normal) encola, mira la cola y resuelve las dudosas.
  · EL AGENTE DEL PC (token de agente) reclama filas y reporta lo que pasó
    en el portal. Nunca recibe credenciales: solo QUÉ radicar.

La decisión vive en `app/services/radicacion_eps.py`; aquí solo se recibe,
se valida y se responde. Arquitectura: docs/ARQUITECTURA_V3_PILAR1_RPA.md
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_auditor_o_superior, get_coordinador_o_admin
from app.api.routers.lotes import verificar_token_agente
from app.database import get_db
from app.models.db import RAD_ESTADOS_VIVOS, RadicacionEpsRecord, UsuarioRecord
from app.services import radicacion_eps as svc

router = APIRouter(prefix="/radicacion", tags=["radicacion-eps"])


# ── Lo que entra ────────────────────────────────────────────────────────
class EncolarIn(BaseModel):
    glosa_ids: list[int] = Field(..., min_length=1, max_length=500)
    trabajo_bot_id: Optional[int] = None


class ReclamarIn(BaseModel):
    portal: str = Field(..., min_length=2, max_length=60)
    equipo: str = Field(..., min_length=2, max_length=200)
    trabajo_bot_id: Optional[int] = None


class RadicadaIn(BaseModel):
    radicado_numero: str = Field(..., min_length=1, max_length=120)
    comprobante_ruta: str = Field(default="", max_length=500)
    comprobante_sha256: str = Field(default="", max_length=64)


class ErrorIn(BaseModel):
    error: str = Field(..., min_length=1, max_length=4000)


class VerificacionIn(BaseModel):
    quedo_radicada: bool
    radicado_numero: str = Field(default="", max_length=120)


# ── Lo que sale ─────────────────────────────────────────────────────────
class FilaDTO(BaseModel):
    id: int
    glosa_id: int
    eps: str = ""
    portal: str = ""
    estado: str = ""
    intentos: int = 0
    radicado_numero: str = ""
    comprobante_sha256: str = ""
    ultimo_error: str = ""
    creado_en: Optional[str] = None
    radicado_en: Optional[str] = None
    actor: str = ""


def _dto(f: RadicacionEpsRecord) -> FilaDTO:
    return FilaDTO(
        id=f.id,
        glosa_id=f.glosa_id,
        eps=f.eps or "",
        portal=f.portal or "",
        estado=f.estado or "",
        intentos=f.intentos or 0,
        radicado_numero=f.radicado_numero or "",
        comprobante_sha256=f.comprobante_sha256 or "",
        ultimo_error=(f.ultimo_error or "")[:400],
        creado_en=f.creado_en.isoformat() if f.creado_en else None,
        radicado_en=f.radicado_en.isoformat() if f.radicado_en else None,
        actor=f.actor or "",
    )


# ══ Puerta del auditor ══════════════════════════════════════════════════


@router.post("/encolar", summary="Mandar glosas al libro de radicación")
def encolar(
    body: EncolarIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """No abre ningún navegador: solo apunta qué hay que radicar.

    Lo que no pasa los escudos se devuelve rechazado CON SU MOTIVO — nada se
    cae en silencio. Los portales con captcha o token nacen en
    HUMANO_REQUERIDO: los hace una persona.
    """
    return svc.encolar(db, body.glosa_ids, trabajo_bot_id=body.trabajo_bot_id)


@router.get("/cola", summary="Estado del libro de radicación")
def cola(
    estado: Optional[str] = Query(None),
    portal: Optional[str] = Query(None),
    limite: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    q = db.query(RadicacionEpsRecord)
    if estado:
        q = q.filter(RadicacionEpsRecord.estado == estado.upper())
    if portal:
        q = q.filter(RadicacionEpsRecord.portal == portal.upper())
    filas = q.order_by(RadicacionEpsRecord.id.desc()).limit(limite).all()
    conteo: dict[str, int] = {}
    for f in filas:
        conteo[f.estado or "?"] = conteo.get(f.estado or "?", 0) + 1
    return {
        "total": len(filas),
        "por_estado": conteo,
        "vivas": sum(1 for f in filas if f.estado in RAD_ESTADOS_VIVOS),
        "filas": [_dto(f).model_dump() for f in filas],
    }


@router.post("/{radicacion_id}/verificar", summary="Resolver una radicación dudosa")
def verificar(
    radicacion_id: int,
    body: VerificacionIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """La ÚNICA salida de «no sé si quedó radicada»: una persona mira el
    portal y dice qué pasó. El bot nunca decide esto solo."""
    r = svc.resolver_verificacion(
        db,
        radicacion_id,
        body.quedo_radicada,
        str(getattr(current_user, "email", "") or "humano"),
        body.radicado_numero,
    )
    if r.get("estado") == "no_existe":
        raise HTTPException(404, "No existe esa radicación.")
    if r.get("estado") == "no_requiere_verificacion":
        raise HTTPException(
            409, f"Esa radicación está en {r.get('actual')}, no requiere verificación."
        )
    return r


# ══ Puerta del agente del PC (token, no sesión) ═════════════════════════


@router.post("/reclamar", summary="El bot pide UNA glosa para radicar")
def reclamar(
    body: ReclamarIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    """Reclamo atómico: dos agentes no pueden llevarse la misma fila.

    Devuelve 204 cuando no hay nada pendiente para ese portal.
    """
    from fastapi import Response

    fila = svc.reclamar_una(
        db, body.portal.upper(), body.equipo, trabajo_bot_id=body.trabajo_bot_id
    )
    if fila is None:
        return Response(status_code=204)
    return fila


@router.post("/{radicacion_id}/en-portal", summary="Se va a pulsar radicar AHORA")
def en_portal(
    radicacion_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    """Se marca ANTES de pulsar. Si el bot muere en el siguiente instante, la
    fila ya quedó como dudosa y nadie la reintentará a ciegas."""
    r = svc.marcar_en_portal(db, radicacion_id)
    if r.get("estado") == "no_existe":
        raise HTTPException(404, "No existe esa radicación.")
    return r


@router.post("/{radicacion_id}/radicada", summary="El portal devolvió el comprobante")
def radicada(
    radicacion_id: int,
    body: RadicadaIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    r = svc.confirmar_radicada(
        db,
        radicacion_id,
        body.radicado_numero,
        body.comprobante_ruta,
        body.comprobante_sha256,
    )
    if r.get("estado") == "no_existe":
        raise HTTPException(404, "No existe esa radicación.")
    if r.get("estado") == "sin_radicado":
        raise HTTPException(422, r.get("detalle", "Falta el número de radicado."))
    return r


@router.post("/{radicacion_id}/fallida", summary="Falló sin alcanzar a enviar")
def fallida(
    radicacion_id: int,
    body: ErrorIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    """Si la fila venía de «no sé si quedó», NO cae a fallida: pasa a
    verificación manual. Reintentar desde la duda es lo que duplica."""
    r = svc.marcar_fallida(db, radicacion_id, body.error)
    if r.get("estado") == "no_existe":
        raise HTTPException(404, "No existe esa radicación.")
    return r


@router.post("/{radicacion_id}/rescatar", summary="El bot se cayó con la fila en la mano")
def rescatar(
    radicacion_id: int,
    body: ErrorIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    """Devuelve a la cola una fila que quedó RECLAMADA por una caída temprana
    del bot (playwright sin instalar, Chrome sin abrir, el navegador que no
    arranca), para que otro equipo sano la tome.

    A los 3 intentos deja de rebotar y pasa a HUMANO_REQUERIDO. Una fila que
    ya salió de RECLAMADA no se toca: responde `no_rescatable` y dice en qué
    estado está — nunca se trae de vuelta algo que ya se pulsó en el portal.
    """
    r = svc.rescatar_reclamada(db, radicacion_id, body.error)
    if r.get("estado") == "no_existe":
        raise HTTPException(404, "No existe esa radicación.")
    return r


@router.post("/{radicacion_id}/humano-requerido", summary="No es automatizable")
def humano_requerido(
    radicacion_id: int,
    body: ErrorIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    r = svc.marcar_humano_requerido(db, radicacion_id, body.error)
    if r.get("estado") == "no_existe":
        raise HTTPException(404, "No existe esa radicación.")
    return r
