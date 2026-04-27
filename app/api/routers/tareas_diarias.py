"""Checklist de tareas diarias del gestor.

NO toca el motor de glosas. Es una herramienta de productividad
personal: cada usuario crea su propia lista del día y va marcando
lo que completa.

Endpoints:
  POST   /usuarios/yo/tareas              — crear tarea
  GET    /usuarios/yo/tareas?fecha=...    — listar (default: hoy)
  GET    /usuarios/yo/tareas/resumen      — contadores rápidos
  PATCH  /usuarios/yo/tareas/{id}         — toggle/edit
  DELETE /usuarios/yo/tareas/{id}         — eliminar
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import TareaDiariaRecord, UsuarioRecord

router = APIRouter(tags=["tareas-diarias"])

PRIORIDADES_VALIDAS = {"ALTA", "MEDIA", "BAJA"}


class TareaIn(BaseModel):
    titulo: str = Field(..., min_length=2, max_length=200)
    descripcion: Optional[str] = Field(None, max_length=1000)
    prioridad: str = Field("MEDIA")
    # ISO YYYY-MM-DD; default = hoy
    fecha_para: Optional[str] = None
    glosa_id: Optional[int] = None


class TareaPatchIn(BaseModel):
    titulo: Optional[str] = Field(None, min_length=2, max_length=200)
    descripcion: Optional[str] = Field(None, max_length=1000)
    prioridad: Optional[str] = None
    fecha_para: Optional[str] = None
    completada: Optional[bool] = None


def _hoy_iso() -> str:
    return date.today().isoformat()


def _validar_fecha(s: Optional[str]) -> str:
    if not s:
        return _hoy_iso()
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "fecha_para debe ser YYYY-MM-DD")
    return s


def _validar_prioridad(p: Optional[str]) -> str:
    if not p:
        return "MEDIA"
    pu = p.upper().strip()
    if pu not in PRIORIDADES_VALIDAS:
        raise HTTPException(
            400, f"prioridad debe ser una de {sorted(PRIORIDADES_VALIDAS)}",
        )
    return pu


def _to_dict(t: TareaDiariaRecord) -> dict:
    return {
        "id": t.id,
        "titulo": t.titulo,
        "descripcion": t.descripcion,
        "prioridad": t.prioridad,
        "fecha_para": t.fecha_para,
        "completada": bool(t.completada),
        "creado_en": t.creado_en.isoformat() if t.creado_en else None,
        "completada_en": (
            t.completada_en.isoformat() if t.completada_en else None
        ),
        "glosa_id": t.glosa_id,
    }


@router.post("/usuarios/yo/tareas", status_code=201)
def crear_tarea(
    body: TareaIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    fecha = _validar_fecha(body.fecha_para)
    prioridad = _validar_prioridad(body.prioridad)
    t = TareaDiariaRecord(
        usuario_email=current_user.email,
        titulo=body.titulo.strip(),
        descripcion=(body.descripcion or "").strip() or None,
        prioridad=prioridad,
        fecha_para=fecha,
        completada=0,
        glosa_id=body.glosa_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_dict(t)


@router.get("/usuarios/yo/tareas")
def listar_tareas(
    fecha: Optional[str] = None,
    incluir_completadas: bool = True,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    f = _validar_fecha(fecha)
    q = (
        db.query(TareaDiariaRecord)
        .filter(TareaDiariaRecord.usuario_email == current_user.email)
        .filter(TareaDiariaRecord.fecha_para == f)
    )
    if not incluir_completadas:
        q = q.filter(TareaDiariaRecord.completada == 0)
    rows = q.order_by(
        TareaDiariaRecord.completada.asc(),
        TareaDiariaRecord.creado_en.asc(),
    ).all()
    pendientes = sum(1 for r in rows if not r.completada)
    return {
        "fecha": f,
        "total": len(rows),
        "pendientes": pendientes,
        "completadas": len(rows) - pendientes,
        "items": [_to_dict(r) for r in rows],
    }


@router.get("/usuarios/yo/tareas/resumen")
def resumen_tareas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Contadores rápidos para badge del botón."""
    hoy = _hoy_iso()
    rows = (
        db.query(TareaDiariaRecord)
        .filter(TareaDiariaRecord.usuario_email == current_user.email)
        .filter(TareaDiariaRecord.fecha_para == hoy)
        .all()
    )
    pendientes = sum(1 for r in rows if not r.completada)
    return {
        "fecha": hoy,
        "total": len(rows),
        "pendientes": pendientes,
        "completadas": len(rows) - pendientes,
    }


@router.patch("/usuarios/yo/tareas/{tarea_id}")
def actualizar_tarea(
    tarea_id: int,
    body: TareaPatchIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    t = (
        db.query(TareaDiariaRecord)
        .filter(TareaDiariaRecord.id == tarea_id)
        .filter(TareaDiariaRecord.usuario_email == current_user.email)
        .first()
    )
    if not t:
        raise HTTPException(404, "Tarea no encontrada")

    if body.titulo is not None:
        t.titulo = body.titulo.strip()
    if body.descripcion is not None:
        t.descripcion = body.descripcion.strip() or None
    if body.prioridad is not None:
        t.prioridad = _validar_prioridad(body.prioridad)
    if body.fecha_para is not None:
        t.fecha_para = _validar_fecha(body.fecha_para)
    if body.completada is not None:
        t.completada = 1 if body.completada else 0
        t.completada_en = ahora_utc() if body.completada else None

    db.commit()
    db.refresh(t)
    return _to_dict(t)


@router.delete("/usuarios/yo/tareas/{tarea_id}", status_code=204)
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    t = (
        db.query(TareaDiariaRecord)
        .filter(TareaDiariaRecord.id == tarea_id)
        .filter(TareaDiariaRecord.usuario_email == current_user.email)
        .first()
    )
    if not t:
        raise HTTPException(404, "Tarea no encontrada")
    db.delete(t)
    db.commit()
    return None
