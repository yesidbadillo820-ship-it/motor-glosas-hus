"""Notas crédito de glosas aceptadas (parcial o total).

Cuando el gestor acepta una glosa — parcial o totalmente — debe
emitir una nota crédito que reduce el valor de la factura original
en el sistema contable. Este router permite registrar el número de
esa nota crédito desde "Mis glosas respondidas".

Endpoints:
  PATCH  /glosas/{id}/nota-credito         — guardar/actualizar
  GET    /glosas/{id}/nota-credito         — consultar
  DELETE /glosas/{id}/nota-credito         — borrar (corrección)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord

router = APIRouter(tags=["nota-credito"])


class NotaCreditoIn(BaseModel):
    numero_nota: str = Field(..., min_length=1, max_length=60)
    fecha_nota: Optional[str] = Field(None)  # ISO YYYY-MM-DD
    valor: Optional[float] = Field(None, ge=0)
    observacion: Optional[str] = Field(None, max_length=500)


def _to_dict(g: GlosaRecord) -> dict:
    return {
        "glosa_id": g.id,
        "factura": g.factura,
        "valor_objetado": g.valor_objetado or 0.0,
        "valor_aceptado": g.valor_aceptado or 0.0,
        "estado": g.estado,
        "numero_nota_credito": g.numero_nota_credito,
        "fecha_nota_credito": (
            g.fecha_nota_credito.isoformat()
            if g.fecha_nota_credito else None
        ),
        "valor_nota_credito": g.valor_nota_credito or 0.0,
        "observacion": g.nota_credito_observacion,
    }


def _validar_fecha(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "fecha_nota debe ser YYYY-MM-DD")


def _glosa_o_404(db: Session, glosa_id: int) -> GlosaRecord:
    g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not g:
        raise HTTPException(404, "Glosa no encontrada")
    return g


@router.patch("/glosas/{glosa_id}/nota-credito")
def guardar_nota_credito(
    glosa_id: int,
    body: NotaCreditoIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    g = _glosa_o_404(db, glosa_id)
    # Solo tiene sentido cuando hay aceptación (parcial o total).
    if (g.valor_aceptado or 0.0) <= 0:
        raise HTTPException(
            400,
            "La glosa no tiene valor aceptado registrado. "
            "Marca primero la aceptación parcial/total.",
        )
    g.numero_nota_credito = body.numero_nota.strip()
    fecha = _validar_fecha(body.fecha_nota)
    g.fecha_nota_credito = fecha or ahora_utc()
    if body.valor is not None and body.valor > 0:
        g.valor_nota_credito = float(body.valor)
    elif (g.valor_nota_credito or 0.0) <= 0:
        # Default razonable: el monto aceptado.
        g.valor_nota_credito = float(g.valor_aceptado or 0.0)
    if body.observacion is not None:
        g.nota_credito_observacion = (body.observacion or "").strip() or None
    db.commit()
    db.refresh(g)
    return _to_dict(g)


@router.get("/glosas/{glosa_id}/nota-credito")
def consultar_nota_credito(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    g = _glosa_o_404(db, glosa_id)
    return _to_dict(g)


@router.delete("/glosas/{glosa_id}/nota-credito", status_code=204)
def borrar_nota_credito(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    g = _glosa_o_404(db, glosa_id)
    g.numero_nota_credito = None
    g.fecha_nota_credito = None
    g.valor_nota_credito = 0.0
    g.nota_credito_observacion = None
    db.commit()
    return None
