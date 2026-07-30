"""Constructor de Agentes: el sistema arma agentes, nadie los programa.

Un agente es una FICHA guardada: nombre, misión, instrucciones propias y
las herramientas del asistente que tiene permitidas. Correrlo es invocar
el MISMO runner del asistente maestro con esa ficha encima — así un agente
nuevo hereda todas las capacidades del sistema (expediente, malla,
diagnóstico, soportes…) sin una línea de código nueva.

Cada corrida queda en la auditoría: quién corrió qué agente, con qué
pregunta y qué herramientas usó.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_auditor_o_superior, get_coordinador_o_admin, get_usuario_actual
from app.core.config import get_settings
from app.database import get_db
from app.models.db import AgenteRecord, UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.services.rate_limit_ia import consumir_cupo_ia as _consumir_cupo_ia

router = APIRouter(prefix="/agentes", tags=["agentes"])

# Plantillas de fábrica: puntos de partida de un clic; el auditor las
# ajusta y guarda como suyas. No son agentes fijos — son sugerencias.
PLANTILLAS = (
    {
        "nombre": "Vigilante de vencimientos",
        "mision": (
            "Vigilar la plata en riesgo: revisar qué glosas están vencidas o por "
            "vencer y decir exactamente cuáles responder primero y por qué."
        ),
        "instrucciones": (
            "Corré siempre diagnostico_operacion primero. Ordená por plata en "
            "riesgo. Para cada glosa urgente, da el ID y el siguiente paso concreto."
        ),
        "herramientas": ["diagnostico_operacion", "buscar_glosa_en_bd", "consultar_expediente"],
    },
    {
        "nombre": "Preparador de mesa",
        "mision": (
            "Dejar una conciliación lista: para un pagador o una factura, armar el "
            "panorama completo antes de la audiencia."
        ),
        "instrucciones": (
            "Usá perfil_pagador para saber qué se puede hacer, consultar_malla_contractual "
            "para el contrato del día del hecho y consultar_expediente por cada factura. "
            "Cerrá con la lista de lo que falta para la mesa."
        ),
        "herramientas": [
            "perfil_pagador",
            "consultar_malla_contractual",
            "consultar_expediente",
            "buscar_glosa_en_bd",
        ],
    },
)


class AgenteIn(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=120)
    mision: str = Field(..., min_length=10, max_length=2000)
    instrucciones: str = Field(default="", max_length=4000)
    herramientas: list[str] = Field(default_factory=list, max_length=20)


class CorrerIn(BaseModel):
    pregunta: str = Field(..., min_length=3, max_length=4000)


def _herramientas_validas() -> dict[str, str]:
    from app.services.asistente_maestro import TOOLS_ASISTENTE

    return {t["name"]: t["description"][:160] for t in TOOLS_ASISTENTE}


def _como_dict(a: AgenteRecord) -> dict:
    try:
        herramientas = json.loads(a.herramientas or "[]")
    except Exception:
        herramientas = []
    return {
        "id": a.id,
        "nombre": a.nombre,
        "mision": a.mision,
        "instrucciones": a.instrucciones or "",
        "herramientas": herramientas,
        "creado_por": a.creado_por,
        "creado_en": a.creado_en.isoformat() if a.creado_en else None,
    }


@router.get("")
def listar_agentes(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Los agentes construidos + el catálogo de herramientas disponibles +
    las plantillas de fábrica para arrancar con un clic."""
    filas = db.query(AgenteRecord).filter(AgenteRecord.activo == 1).order_by(AgenteRecord.id).all()
    return {
        "agentes": [_como_dict(a) for a in filas],
        "herramientas_disponibles": _herramientas_validas(),
        "plantillas": list(PLANTILLAS),
    }


@router.post("")
def crear_agente(
    data: AgenteIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Construir un agente = guardar su ficha. Sin código."""
    validas = _herramientas_validas()
    desconocidas = [h for h in data.herramientas if h not in validas]
    if desconocidas:
        raise HTTPException(400, f"Herramientas desconocidas: {', '.join(desconocidas)}")
    if not data.herramientas:
        raise HTTPException(400, "Un agente necesita al menos una herramienta permitida")

    a = AgenteRecord(
        nombre=data.nombre.strip(),
        mision=data.mision.strip(),
        instrucciones=data.instrucciones.strip(),
        herramientas=json.dumps(data.herramientas, ensure_ascii=False),
        creado_por=current_user.email,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="AGENTE_CREADO",
            tabla="agentes",
            registro_id=a.id,
            valor_nuevo=a.nombre[:200],
            detalle=json.dumps(
                {"mision": a.mision[:300], "herramientas": data.herramientas},
                ensure_ascii=False,
            )[:1900],
        )
        db.commit()
    except Exception:
        pass
    return _como_dict(a)


@router.post("/{agente_id}/correr")
async def correr_agente(
    agente_id: int,
    data: CorrerIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
    _cupo_ia: None = Depends(_consumir_cupo_ia),
):
    """Correr el agente: el runner del asistente con la ficha encima.

    La misión y las instrucciones van como sistema adicional; las
    herramientas se recortan a las permitidas por la ficha.
    """
    a = db.get(AgenteRecord, agente_id)
    if not a or not a.activo:
        raise HTTPException(404, "Ese agente no existe o fue retirado")

    from app.services.asistente_maestro import chat_con_asistente

    try:
        herramientas = json.loads(a.herramientas or "[]")
    except Exception:
        herramientas = []

    cfg = get_settings()
    system_extra = (
        f"AGENTE ACTIVO: {a.nombre}\nMISIÓN DEL AGENTE: {a.mision}"
        + (f"\nINSTRUCCIONES DEL AGENTE: {a.instrucciones}" if a.instrucciones else "")
        + "\nActuá SOLO dentro de esa misión y con las herramientas que tenés."
    )
    resultado = await chat_con_asistente(
        mensajes=[{"role": "user", "content": data.pregunta}],
        db=db,
        current_user=current_user,
        api_key=cfg.anthropic_api_key or None,
        modelo=cfg.anthropic_model or None,
        system_extra=system_extra,
        tools_permitidas=herramientas,
    )
    if resultado.get("error"):
        raise HTTPException(502, resultado["error"])

    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="AGENTE_CORRIDO",
            tabla="agentes",
            registro_id=a.id,
            campo=a.nombre[:100],
            detalle=json.dumps(
                {
                    "pregunta": data.pregunta[:300],
                    "tools_usadas": [t.get("name") for t in resultado.get("tools_llamadas", [])],
                },
                ensure_ascii=False,
            )[:1900],
        )
        db.commit()
    except Exception:
        pass

    return {
        "agente": a.nombre,
        "respuesta": resultado.get("respuesta", ""),
        "tools_llamadas": resultado.get("tools_llamadas", []),
    }


@router.delete("/{agente_id}")
def retirar_agente(
    agente_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Retirar (no borrar): la ficha queda para la trazabilidad."""
    a = db.get(AgenteRecord, agente_id)
    if not a or not a.activo:
        raise HTTPException(404, "Ese agente no existe o ya fue retirado")
    a.activo = 0
    db.commit()
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="AGENTE_RETIRADO",
            tabla="agentes",
            registro_id=a.id,
            valor_anterior=a.nombre[:200],
        )
        db.commit()
    except Exception:
        pass
    return {"ok": True, "retirado": a.nombre}
