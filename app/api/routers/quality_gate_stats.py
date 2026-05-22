"""Endpoint de estadísticas del Quality Gate.

Para que el coordinador visualice:
  - Estado del Quality Gate (activo/inactivo)
  - % de rollout configurado
  - Capacidades disponibles (modelos detectados)
  - Configuración resumida

Endpoint público para SUPER_ADMIN. Útil para verificar que el deploy
trae los cambios y para decidir cuándo subir el rollout %.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_coordinador_o_admin
from app.models.db import UsuarioRecord
from app.services.quality_gate_adapter import (
    es_quality_gate_activo,
    porcentaje_rollout,
)

router = APIRouter(prefix="/sistema", tags=["sistema-quality-gate"])


class QualityGateStatus(BaseModel):
    activo: bool
    porcentaje_rollout: int
    proveedores_configurados: dict[str, bool]
    descripcion: str
    componentes: dict[str, str]


@router.get("/quality-gate", response_model=QualityGateStatus)
def estado_quality_gate(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
) -> QualityGateStatus:
    """Estado actual del Quality Gate y su configuración.

    Solo coordinadores/admins pueden ver esta información.
    """
    activo = es_quality_gate_activo()
    pct = porcentaje_rollout()

    proveedores = {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
        "groq": bool(os.environ.get("GROQ_API_KEY", "")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY", "")),
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY", "")),
    }

    if activo:
        descripcion = (
            f"Quality Gate ACTIVO. {pct}% de los dictámenes se procesan con "
            f"pipeline determinístico (pre-val → IA → post-val → "
            f"regenerar con otro modelo si falla → escalar a humano si tras "
            f"3 intentos no aprueba)."
        )
    else:
        descripcion = (
            "Quality Gate INACTIVO. Los módulos están instalados pero NO se "
            "están usando — los dictámenes siguen el flujo legacy. "
            "Activar con env var QUALITY_GATE_ENABLED=1."
        )

    componentes = {
        "pre_validator": "app/services/quality_gate/pre_validator.py — 49 tests",
        "post_validator": "app/services/quality_gate/post_validator.py — 24 tests",
        "orchestrator": "app/services/quality_gate/orchestrator.py — 9 tests",
        "ia_router": "app/services/ia_router.py — 23 tests",
        "inteligencia_ambiental": "app/services/inteligencia_ambiental.py — 18 tests",
        "asistente_predictivo": "POST /asistente/predecir (Ola 4)",
        "design_system": "static/sinac-ds.css + sinac-ux.js (Modo Enfocado + ⌘K)",
    }

    return QualityGateStatus(
        activo=activo,
        porcentaje_rollout=pct,
        proveedores_configurados=proveedores,
        descripcion=descripcion,
        componentes=componentes,
    )
