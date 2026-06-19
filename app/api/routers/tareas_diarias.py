"""Checklist de tareas diarias del gestor."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import TareaDiariaRecord, UsuarioRecord

router = APIRouter(prefix="/usuarios/yo/tareas", tags=["tareas"])

_PRIORIDADES_VALIDAS = {"ALTA", "MEDIA", "BAJA"}


class TareaIn(BaseModel):
    titulo: str
    descripcion: str | None = None
    prioridad: str = "MEDIA"
    fecha_para: str | None = None
    glosa_id: int | None = None


class TareaPatch(BaseModel):
    titulo: str | None = None
    descripcion: str | None = None
    prioridad: str | None = None
    completada: bool | None = None


def _validar_tarea_in(body: TareaIn) -> None:
    if body.prioridad.upper() not in _PRIORIDADES_VALIDAS:
        raise HTTPException(status_code=400, detail="prioridad debe ser ALTA, MEDIA o BAJA")
    if body.fecha_para is not None:
        try:
            date.fromisoformat(body.fecha_para)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="fecha_para no es una fecha ISO válida")


def _serialize(t: TareaDiariaRecord) -> dict:
    return {
        "id": t.id,
        "titulo": t.titulo,
        "descripcion": t.descripcion,
        "prioridad": t.prioridad,
        "fecha_para": t.fecha_para,
        "completada": bool(t.completada),
        "completada_en": t.completada_en.isoformat() if t.completada_en else None,
        "glosa_id": t.glosa_id,
        "creado_en": t.creado_en.isoformat() if t.creado_en else None,
    }


@router.post("", status_code=201)
def crear_tarea(
    body: TareaIn,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    _validar_tarea_in(body)
    tarea = TareaDiariaRecord(
        usuario_email=usuario.email,
        titulo=body.titulo,
        descripcion=body.descripcion,
        prioridad=body.prioridad.upper(),
        fecha_para=body.fecha_para or date.today().isoformat(),
        completada=0,
        glosa_id=body.glosa_id,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    return _serialize(tarea)


@router.get("/resumen")
def resumen_hoy(
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    hoy = date.today().isoformat()
    q = db.query(TareaDiariaRecord).filter(
        TareaDiariaRecord.usuario_email == usuario.email,
        TareaDiariaRecord.fecha_para == hoy,
    )
    items = q.all()
    pendientes = sum(1 for t in items if not t.completada)
    completadas = sum(1 for t in items if t.completada)
    return {"total": len(items), "pendientes": pendientes, "completadas": completadas}


@router.get("")
def listar_tareas(
    fecha: str | None = None,
    incluir_completadas: bool = True,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    fecha_filtro = fecha or date.today().isoformat()
    q = db.query(TareaDiariaRecord).filter(
        TareaDiariaRecord.usuario_email == usuario.email,
        TareaDiariaRecord.fecha_para == fecha_filtro,
    )
    if not incluir_completadas:
        q = q.filter(TareaDiariaRecord.completada == 0)
    items = q.all()
    return {"total": len(items), "items": [_serialize(t) for t in items]}


@router.patch("/{tarea_id}")
def actualizar_tarea(
    tarea_id: int,
    body: TareaPatch,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    tarea = (
        db.query(TareaDiariaRecord)
        .filter(
            TareaDiariaRecord.id == tarea_id,
            TareaDiariaRecord.usuario_email == usuario.email,
        )
        .first()
    )
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    if body.titulo is not None:
        tarea.titulo = body.titulo
    if body.descripcion is not None:
        tarea.descripcion = body.descripcion
    if body.prioridad is not None:
        if body.prioridad.upper() not in _PRIORIDADES_VALIDAS:
            raise HTTPException(status_code=400, detail="prioridad debe ser ALTA, MEDIA o BAJA")
        tarea.prioridad = body.prioridad.upper()
    if body.completada is not None:
        tarea.completada = 1 if body.completada else 0
        if body.completada:
            tarea.completada_en = datetime.now(timezone.utc)
        else:
            tarea.completada_en = None
    db.commit()
    db.refresh(tarea)
    return _serialize(tarea)


@router.delete("/{tarea_id}", status_code=204)
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    usuario: UsuarioRecord = Depends(get_usuario_actual),
):
    tarea = (
        db.query(TareaDiariaRecord)
        .filter(
            TareaDiariaRecord.id == tarea_id,
            TareaDiariaRecord.usuario_email == usuario.email,
        )
        .first()
    )
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    db.delete(tarea)
    db.commit()
