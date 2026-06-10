"""Endpoint de estadísticas del Quality Gate.

Para que el coordinador visualice:
  - Estado del Quality Gate (activo/inactivo)
  - % de rollout configurado
  - Capacidades disponibles (modelos detectados)
  - Estadísticas reales (BD): tasa de aprobación, scores, modelos
  - Endpoint de prueba para validar el sistema sin gastar IA real

Endpoint público para SUPER_ADMIN. Útil para verificar que el deploy
trae los cambios y para decidir cuándo subir el rollout %.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.quality_gate import post_validar_dictamen, pre_validar_glosa
from app.services.quality_gate_adapter import (
    es_quality_gate_activo,
    porcentaje_rollout,
)
from app.services.quality_gate_recorder import estadisticas_recientes

router = APIRouter(prefix="/sistema", tags=["sistema-quality-gate"])


class QualityGateStatus(BaseModel):
    activo: bool
    porcentaje_rollout: int
    proveedores_configurados: dict[str, bool]
    descripcion: str
    componentes: dict[str, str]
    estadisticas: dict


class QualityGateTestInput(BaseModel):
    eps: str
    codigo_glosa: str
    valor_objetado: str | int | float
    texto_glosa: str
    es_ratificacion: bool = False
    dictamen_a_validar: str = ""  # opcional, para probar post-val sin IA


class QualityGateTestResponse(BaseModel):
    pre_validation: dict
    post_validation: dict | None
    resumen: str


@router.get("/quality-gate", response_model=QualityGateStatus)
def estado_quality_gate(
    dias: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
) -> QualityGateStatus:
    """Estado actual del Quality Gate y su configuración.

    Incluye estadísticas reales de la BD si hay runs registrados.
    Solo coordinadores/admins pueden ver esta información.
    """
    activo = es_quality_gate_activo()
    pct = porcentaje_rollout()

    proveedores = {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
        "groq": bool(os.environ.get("GROQ_API_KEY", "")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY", "")),
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
        "recorder": "app/services/quality_gate_recorder.py — persistencia BD",
    }

    # Estadísticas reales (puede ser vacío si recién instalado)
    stats = estadisticas_recientes(db, dias=dias)

    return QualityGateStatus(
        activo=activo,
        porcentaje_rollout=pct,
        proveedores_configurados=proveedores,
        descripcion=descripcion,
        componentes=componentes,
        estadisticas=stats,
    )


@router.post("/quality-gate/test", response_model=QualityGateTestResponse)
def probar_quality_gate(
    payload: QualityGateTestInput,
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
) -> QualityGateTestResponse:
    """Prueba el Quality Gate con inputs específicos SIN llamar a IA real.

    Útil para validar que:
      - Pre-validador acepta/rechaza inputs correctamente
      - Post-validador detecta citas inventadas / coda procesal

    Si `dictamen_a_validar` está vacío, sólo corre pre-validación.
    """
    # Pre-validación
    pre = pre_validar_glosa(
        eps=payload.eps,
        codigo_glosa=payload.codigo_glosa,
        valor_objetado=payload.valor_objetado,
        texto_glosa=payload.texto_glosa,
    )

    pre_dict = {
        "aprobado": pre.aprobado,
        "codigo_normalizado": pre.codigo_normalizado,
        "familia_codigo": pre.familia_codigo,
        "eps_normalizada": pre.eps_normalizada,
        "valor_parseado": pre.valor_parseado,
        "razones_bloqueo": pre.razones_bloqueo,
        "sugerencias": pre.sugerencias,
        "mensaje_para_usuario": pre.mensaje_para_usuario,
    }

    post_dict = None
    resumen_parts: list[str] = []
    resumen_parts.append(
        f"PRE: {'✅ aprobado' if pre.aprobado else '❌ rechazado'} — "
        f"código '{pre.codigo_normalizado}' familia '{pre.familia_codigo}', "
        f"valor ${pre.valor_parseado:,.0f}"
    )

    if payload.dictamen_a_validar:
        post = post_validar_dictamen(
            payload.dictamen_a_validar,
            eps=pre.eps_normalizada,
            es_ratificacion=payload.es_ratificacion,
        )
        post_dict = {
            "aprobado": post.aprobado,
            "score": post.score,
            "debe_regenerar": post.debe_regenerar,
            "razones_rechazo": post.razones_rechazo,
            "checks": {
                k: {"ok": v.ok, "severidad": v.severidad, "razon": v.razon}
                for k, v in post.checks.items()
            },
            "citas_problematicas": [
                {"cita": c.get("cita", ""), "tipo": c.get("tipo", "")}
                for c in post.citas_problematicas[:5]
            ],
        }
        resumen_parts.append(
            f"POST: {'✅ aprobado' if post.aprobado else '❌ rechazado'} — score {post.score}/100"
        )

    return QualityGateTestResponse(
        pre_validation=pre_dict,
        post_validation=post_dict,
        resumen=" | ".join(resumen_parts),
    )
