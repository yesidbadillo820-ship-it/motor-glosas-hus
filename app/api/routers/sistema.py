"""Router de salud del sistema (Ronda 17).

Endpoints:
  GET /sistema/salud
    Reporte consolidado de BD + scheduler + bots + anomalías + métricas.
    Solo coordinador / super admin.

  GET /sistema/salud/publico
    Versión liviana sin datos sensibles: solo estado_general + timestamp.
    Sirve como healthcheck para monitoreo externo (Render, UptimeRobot).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.health_monitor import checar_salud

router = APIRouter(prefix="/sistema", tags=["sistema"])


@router.get("/salud")
def salud_detallada(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    return checar_salud(db)


@router.get("/salud/publico")
def salud_publica(db: Session = Depends(get_db)):
    """Healthcheck sin autenticación para monitores externos.
    Devuelve solo el estado_general y la hora, sin métricas internas."""
    r = checar_salud(db)
    return {
        "estado": r["estado_general"],
        "generado_en": r["generado_en"],
    }
