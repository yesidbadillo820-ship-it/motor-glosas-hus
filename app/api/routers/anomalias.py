"""Router de anomalías / anti-fraude (Ronda 16).

Expone los detectores de `app.services.detector_anomalias` al dashboard
del coordinador:

  GET /anomalias/dashboard?ventana_dias=30
    → resumen unificado (duplicados + patrones EPS)

  GET /anomalias/glosa/{id}/valor-anomalo
    → z-score del valor de una glosa vs histórico del CUPS
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.services.detector_anomalias import (
    detectar_valor_anomalo,
    resumen_anomalias,
)

router = APIRouter(prefix="/anomalias", tags=["anomalias"])


@router.get("/dashboard")
def dashboard_anomalias(
    ventana_dias: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    return resumen_anomalias(db, ventana_dias=ventana_dias)


@router.get("/glosa/{glosa_id}/valor-anomalo")
def valor_anomalo_de_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Glosa no encontrada")
    a = detectar_valor_anomalo(db, g)
    if a is None:
        return {"anomalia": False, "glosa_id": glosa_id}
    return {"anomalia": True, **a.__dict__}
