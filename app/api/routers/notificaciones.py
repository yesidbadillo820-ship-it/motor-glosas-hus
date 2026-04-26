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


@router.get("/contadores")
def contadores_notificaciones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R158 P1: contadores granulares de notificaciones del usuario.

    Diferente a /badge (solo total): aquí desglose por tipo, útil
    para mostrar pestañas con badges en la UI:
      "Críticas (3) | Vencidas (12) | Plantillas (1)"
    """
    r = notificaciones_de(db, current_user)
    grupos = r.get("grupos", []) if isinstance(r, dict) else []
    desglose = {}
    for g in grupos:
        if isinstance(g, dict):
            tipo = g.get("tipo") or g.get("nombre") or "(sin_tipo)"
            count = (
                g.get("count")
                or g.get("total")
                or len(g.get("items", []))
            )
            desglose[tipo] = count
    return {
        "total": r.get("total", 0) if isinstance(r, dict) else 0,
        "por_tipo": desglose,
        "generado_en": (
            r.get("generado_en") if isinstance(r, dict) else None
        ),
    }


@router.get("/badge")
def badge(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r = notificaciones_de(db, current_user)
    return {"total": r.get("total", 0), "generado_en": r.get("generado_en")}
