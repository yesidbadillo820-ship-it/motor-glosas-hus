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
from app.services.texto_fijo_detector import (
    aplicar_texto_fijo_si_corresponde,
    clasificar_texto_fijo,
)
from app.services.texto_fijo_batch import retro_aplicar

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


@router.get("/texto-fijo/{glosa_id}")
def previsualizar_texto_fijo(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Muestra qué texto fijo aplicaría (Ronda 21). No muta la BD."""
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    clase = clasificar_texto_fijo(g)
    if clase is None:
        return {
            "glosa_id": glosa_id,
            "aplica": False,
            "mensaje": "La glosa no es RATIFICADA ni EXTEMPORÁNEA — requiere análisis IA.",
        }
    return {"glosa_id": glosa_id, "aplica": True, **clase}


@router.post("/texto-fijo/batch")
def batch_texto_fijo(
    dry_run: bool = Query(True, description="Si True, solo reporta — no muta."),
    limite: Optional[int] = Query(None, ge=1, le=5000),
    ventana_dias: int = Query(365, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Retro-aplica el detector a todas las glosas candidatas (Ronda 22).

    Corre una sola vez después del deploy para limpiar el backlog. Es
    idempotente — corridas posteriores no duplican efectos. Recomendado
    correr primero con dry_run=true para revisar los conteos, y luego
    con dry_run=false para ejecutar.
    """
    return retro_aplicar(db, dry_run=dry_run, limite=limite, ventana_dias=ventana_dias)


@router.post("/texto-fijo/{glosa_id}/aplicar")
def aplicar_texto_fijo(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Aplica el texto fijo a la glosa (muta). Solo coordinador/super_admin."""
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    clase = aplicar_texto_fijo_si_corresponde(g)
    if clase is None:
        return {
            "glosa_id": glosa_id,
            "aplicado": False,
            "mensaje": "No aplica texto fijo para esta glosa (o ya tiene dictamen IA).",
        }
    db.commit()
    return {"glosa_id": glosa_id, "aplicado": True, **clase}
