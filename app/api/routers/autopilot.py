"""Router del autopilot de recomendación (Ronda 18).

Expone el servicio `autopilot_service` al frontend:

  GET /autopilot/glosa/{id}
    → evalúa UNA glosa específica y devuelve estado + confianza + razones

  GET /autopilot/bandeja?auditor_email=...
    → evalúa la bandeja (PENDIENTE) del auditor actual (o de otro si es
      coordinador/super_admin). Devuelve conteo por estado + lista completa.

  GET /autopilot/mi-bandeja
    → atajo: fuerza el auditor_email al usuario autenticado.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_coordinador_o_admin
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord, ROL_COORDINADOR, ROL_SUPER_ADMIN
from app.services.autopilot_service import (
    evaluar_bandeja,
    evaluar_glosa_autopilot,
)

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.get("/glosa/{glosa_id}")
def evaluar_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    # Auditores solo pueden evaluar sus propias glosas
    if current_user.rol not in (ROL_COORDINADOR, ROL_SUPER_ADMIN):
        if g.auditor_email and g.auditor_email != current_user.email:
            raise HTTPException(
                status_code=403,
                detail="Solo podés evaluar glosas asignadas a vos.",
            )
    res = evaluar_glosa_autopilot(db, g)
    return {
        "glosa_id": glosa_id,
        "estado_autopilot": res.estado,
        "confianza": res.confianza,
        "razones_a_favor": res.razones_a_favor,
        "razones_en_contra": res.razones_en_contra,
        "acciones_sugeridas": res.acciones_sugeridas,
        "detalle": res.detalle,
    }


@router.get("/bandeja")
def bandeja(
    auditor_email: Optional[str] = Query(None),
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Solo coordinador/super_admin puede mirar bandejas ajenas."""
    return evaluar_bandeja(db, auditor_email=auditor_email, limite=limite)


@router.get("/mi-bandeja")
def mi_bandeja(
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    return evaluar_bandeja(db, auditor_email=current_user.email, limite=limite)
