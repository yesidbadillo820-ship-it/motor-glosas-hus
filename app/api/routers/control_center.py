"""Control Center del coordinador (Ronda 23).

Un único endpoint que combina las vistas que el gestor necesita cada
mañana, para evitar tres round-trips consecutivos desde el frontend:

  GET /control-center/resumen
    {
      "salud": {...},          # health_monitor.checar_salud(db)
      "bandeja": {...},         # autopilot.evaluar_bandeja(db) — conteo + top 20
      "digest_dia": {...},      # digest_ejecutivo.generar_digest(db, 'dia')
      "scheduler_ia":   {...},  # ia_auditora_proactiva.obtener_estado()
      "scheduler_digest": {...} # digest_scheduler.obtener_estado()
    }

Un solo fetch → un dashboard completo. Diseñado para el banner que el
coordinador ve al abrir el sistema.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.autopilot_service import evaluar_bandeja
from app.services.digest_ejecutivo import generar_digest
from app.services.health_monitor import checar_salud

router = APIRouter(prefix="/control-center", tags=["control-center"])


def _estado_scheduler_ia() -> dict:
    try:
        from app.services.ia_auditora_proactiva import obtener_estado
        return obtener_estado()
    except Exception as e:
        return {"error": str(e)[:200]}


def _estado_scheduler_digest() -> dict:
    try:
        from app.services.digest_scheduler import obtener_estado
        return obtener_estado()
    except Exception as e:
        return {"error": str(e)[:200]}


@router.get("/resumen")
def resumen(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Resumen único: salud + bandeja autopilot + digest + schedulers.

    Es el dashboard de 5 segundos — un solo fetch cubre todo lo que el
    coordinador necesita al iniciar el día. Responde rápido: ~6 queries
    agregadas + 1 ping BD + 2 obtener_estado en memoria.
    """
    salud = checar_salud(db)
    try:
        bandeja = evaluar_bandeja(db, auditor_email=None, limite=20)
    except Exception as e:
        bandeja = {"error": str(e)[:200]}
    try:
        digest_dia = generar_digest(db, periodo="dia")
    except Exception as e:
        digest_dia = {"error": str(e)[:200]}

    return {
        "estado_general": salud.get("estado_general", "OK"),
        "generado_en": salud.get("generado_en"),
        "salud": salud,
        "bandeja": bandeja,
        "digest_dia": digest_dia,
        "scheduler_ia": _estado_scheduler_ia(),
        "scheduler_digest": _estado_scheduler_digest(),
    }
