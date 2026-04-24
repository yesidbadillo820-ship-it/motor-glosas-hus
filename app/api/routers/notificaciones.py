"""Router de notificaciones personales (Ronda 25).

GET /notificaciones/mias
  Consolida todo lo que le importa al usuario logueado:
  - glosas críticas / vencidas
  - glosas listas para enviar (texto fijo)
  - menciones sin resolver
  - plantillas Gold nuevas de sus EPS

GET /notificaciones/badge
  Versión ultra-liviana que solo devuelve el número total —
  ideal para llamar cada 30s sin saturar la BD.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.notificaciones_usuario import notificaciones_de

router = APIRouter(prefix="/notificaciones", tags=["notificaciones"])


@router.get("/mias")
def mis_notificaciones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    return notificaciones_de(db, current_user)


@router.get("/badge")
def badge(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r = notificaciones_de(db, current_user)
    return {"total": r.get("total", 0), "generado_en": r.get("generado_en")}
