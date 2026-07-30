"""Los bots del hospital, ADMINISTRADOS desde la plataforma.

Ciclo de vida completo de un trabajo: encolar → reclamar (agente del PC)
→ progreso → finalizar (o error) — con cancelar y reintentar desde la
pantalla. El tablero muestra por bot: estado vivo, cola, última corrida,
equipo, usuario, duración promedio, espera promedio y cuántas van hoy.
Todo queda en la auditoría.

El agente del PC no conoce ningún bot por nombre: recibe el comando desde
el catálogo (bots_hus) al reclamar. Cero if/else por pagador.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_auditor_o_superior, get_usuario_actual
from app.api.routers.lotes import verificar_token_agente
from app.core.tz import a_utc
from app.database import get_db
from app.models.db import TrabajoBotRecord, UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.services import bots_hus

router = APIRouter(prefix="/bots", tags=["bots"])

ESTADOS_ABIERTOS = ("PENDIENTE", "RECLAMADO")


class EjecutarIn(BaseModel):
    parametros: dict = Field(default_factory=dict)


class ReclamarIn(BaseModel):
    equipo: str = Field(..., min_length=2, max_length=200)


class ProgresoIn(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=1000)


class FinalizarIn(BaseModel):
    exito: bool
    registro: str = Field(default="", max_length=20000)
    error: str = Field(default="", max_length=4000)


def _trabajo_dict(t: TrabajoBotRecord) -> dict:
    return {
        "id": t.id,
        "bot_id": t.bot_id,
        "estado": t.estado,
        "pedido_por": t.pedido_por,
        "equipo": t.equipo,
        "parametros": json.loads(t.parametros or "{}"),
        "progreso": t.progreso,
        "creado_en": t.creado_en.isoformat() if t.creado_en else None,
        "reclamado_en": t.reclamado_en.isoformat() if t.reclamado_en else None,
        "terminado_en": t.terminado_en.isoformat() if t.terminado_en else None,
        "cancelado_por": t.cancelado_por,
        "error": (t.error or "")[:1000] or None,
        "registro": (t.registro or "")[:4000] or None,
    }


def _auditar(db, usuario, rol, accion, trabajo, detalle=""):
    try:
        AuditRepository(db).registrar(
            usuario_email=usuario,
            usuario_rol=rol,
            accion=accion,
            tabla="trabajos_bot",
            registro_id=trabajo.id,
            campo=trabajo.bot_id,
            detalle=detalle[:1900],
        )
        db.commit()
    except Exception:
        pass


def _estadisticas(trabajos: list[TrabajoBotRecord]) -> dict:
    """Duración y espera promedio (segundos) + cuántas corridas van hoy."""
    duraciones, esperas = [], []
    hoy = 0
    for t in trabajos:
        if t.reclamado_en and t.terminado_en:
            duraciones.append((a_utc(t.terminado_en) - a_utc(t.reclamado_en)).total_seconds())
        if t.creado_en and t.reclamado_en:
            esperas.append((a_utc(t.reclamado_en) - a_utc(t.creado_en)).total_seconds())
        if t.creado_en and a_utc(t.creado_en).date() == date.today():
            hoy += 1
    return {
        "duracion_promedio_seg": round(sum(duraciones) / len(duraciones)) if duraciones else None,
        "espera_promedio_seg": round(sum(esperas) / len(esperas)) if esperas else None,
        "ejecutadas_hoy": hoy,
    }


def _ficha_viva(b, trabajos: list[TrabajoBotRecord]) -> dict:
    pendientes = [t for t in trabajos if t.estado == "PENDIENTE"]
    corriendo = next((t for t in trabajos if t.estado == "RECLAMADO"), None)
    cerrados = [t for t in trabajos if t.estado in ("TERMINADO", "ERROR", "CANCELADO")]
    ultimo = cerrados[0] if cerrados else None
    ultimo_error = next((t for t in cerrados if t.estado == "ERROR"), None)
    if corriendo:
        estado = "CORRIENDO"
    elif pendientes:
        estado = "EN COLA"
    elif ultimo and ultimo.estado == "ERROR":
        estado = "ERROR"
    else:
        estado = "DISPONIBLE"
    ficha = b.como_dict()
    ficha.update(
        {
            "estado": estado,
            "pendientes": len(pendientes),
            "trabajo_corriendo": _trabajo_dict(corriendo) if corriendo else None,
            "ultima_ejecucion": _trabajo_dict(ultimo) if ultimo else None,
            "ultimo_error": _trabajo_dict(ultimo_error) if ultimo_error else None,
            "total_corridas": len(cerrados),
            **_estadisticas(trabajos),
        }
    )
    return ficha


def _trabajos_por_bot(db) -> dict[str, list[TrabajoBotRecord]]:
    filas = db.query(TrabajoBotRecord).order_by(TrabajoBotRecord.id.desc()).limit(1000).all()
    por_bot: dict[str, list[TrabajoBotRecord]] = {}
    for t in filas:
        por_bot.setdefault(t.bot_id, []).append(t)
    return por_bot


# ─── La cola (rutas literales ANTES de /{bot_id}) ────────────────────────


@router.get("/trabajos")
def cola_de_trabajos(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """La cola completa: lo pendiente, lo que corre y lo último cerrado."""
    filas = db.query(TrabajoBotRecord).order_by(TrabajoBotRecord.id.desc()).limit(100).all()
    abiertos = [t for t in filas if t.estado in ESTADOS_ABIERTOS]
    return {
        "abiertos": [_trabajo_dict(t) for t in abiertos],
        "recientes": [_trabajo_dict(t) for t in filas if t.estado not in ESTADOS_ABIERTOS][:30],
    }


@router.post("/trabajos/reclamar")
def reclamar_trabajo(
    body: ReclamarIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    """El agente del PC pide trabajo: se lleva el pendiente más viejo,
    con el comando que dice el catálogo (el agente no sabe de pagadores)."""
    t = (
        db.query(TrabajoBotRecord)
        .filter(TrabajoBotRecord.estado == "PENDIENTE")
        .order_by(TrabajoBotRecord.id)
        .first()
    )
    if t is None:
        return Response(status_code=204)
    t.estado = "RECLAMADO"
    t.equipo = body.equipo[:200]
    t.reclamado_en = datetime.now(timezone.utc)
    t.progreso = f"Reclamado por {t.equipo}"
    db.commit()
    b = bots_hus.obtener(t.bot_id)
    return {
        "trabajo_id": t.id,
        "bot_id": t.bot_id,
        "comando": b.comando_pc if b else "",
        "parametros": json.loads(t.parametros or "{}"),
    }


@router.get("/trabajos/{trabajo_id}")
def detalle_trabajo(
    trabajo_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    t = db.get(TrabajoBotRecord, trabajo_id)
    if not t:
        raise HTTPException(404, "Trabajo no encontrado")
    d = _trabajo_dict(t)
    d["registro"] = (t.registro or "")[:20000] or None  # acá sí completo
    return d


@router.post("/trabajos/{trabajo_id}/progreso")
def reportar_progreso(
    trabajo_id: int,
    body: ProgresoIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    t = db.get(TrabajoBotRecord, trabajo_id)
    if not t:
        raise HTTPException(404, "Trabajo no encontrado")
    if t.estado != "RECLAMADO":
        raise HTTPException(409, f"El trabajo está en estado {t.estado}, no RECLAMADO")
    t.progreso = body.mensaje[:1000]
    db.commit()
    return {"ok": True}


@router.post("/trabajos/{trabajo_id}/finalizar")
def finalizar_trabajo(
    trabajo_id: int,
    body: FinalizarIn,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    t = db.get(TrabajoBotRecord, trabajo_id)
    if not t:
        raise HTTPException(404, "Trabajo no encontrado")
    if t.estado != "RECLAMADO":
        raise HTTPException(409, f"El trabajo está en estado {t.estado}, no RECLAMADO")
    t.estado = "TERMINADO" if body.exito else "ERROR"
    t.terminado_en = datetime.now(timezone.utc)
    t.registro = body.registro[:20000]
    t.error = (body.error or "")[:4000] or None
    t.progreso = "Terminado" if body.exito else "Falló"
    db.commit()
    _auditar(
        db,
        f"agente@{t.equipo or 'pc'}",
        "AGENTE_PC",
        "BOT_TERMINADO" if body.exito else "BOT_ERROR",
        t,
        (body.error or body.registro or ""),
    )
    return {"ok": True, "estado": t.estado}


# ─── Los bots ────────────────────────────────────────────────────────────


@router.get("")
def tablero_de_bots(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """El tablero completo: cada bot del hospital con su estado vivo."""
    por_bot = _trabajos_por_bot(db)
    grupos: dict[str, list[dict]] = {}
    for b in bots_hus.catalogo():
        grupos.setdefault(b.grupo, []).append(_ficha_viva(b, por_bot.get(b.id, [])))
    abiertos = sum(1 for ts in por_bot.values() for t in ts if t.estado in ESTADOS_ABIERTOS)
    return {
        "total_bots": len(bots_hus.catalogo()),
        "trabajos_abiertos": abiertos,
        "grupos": [{"nombre": g, "bots": bs} for g, bs in grupos.items()],
    }


@router.get("/{bot_id}")
def detalle_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """La ficha viva de UN bot + su historial completo (30 últimas)."""
    b = bots_hus.obtener(bot_id)
    if b is None:
        raise HTTPException(404, f"No existe el bot '{bot_id}'")
    trabajos = (
        db.query(TrabajoBotRecord)
        .filter(TrabajoBotRecord.bot_id == bot_id)
        .order_by(TrabajoBotRecord.id.desc())
        .limit(30)
        .all()
    )
    ficha = _ficha_viva(b, trabajos)
    ficha["historial"] = [_trabajo_dict(t) for t in trabajos]
    return ficha


@router.post("/{bot_id}/ejecutar")
def ejecutar_bot(
    bot_id: str,
    data: EjecutarIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Encola el bot. Los de nube remiten a su conversor; los de lotes, a
    la pantalla Lotes (esa cola ya existe y funciona)."""
    b = bots_hus.obtener(bot_id)
    if b is None:
        raise HTTPException(404, f"No existe el bot '{bot_id}'")
    if b.disparo == "automatizacion":
        return {
            "encolado": False,
            "motivo": "nube",
            "mensaje": "Este corre en la nube: usá su tarjeta de conversores (subir archivo → descargar).",
            "automatizacion_id": b.automatizacion_id,
        }
    if b.disparo == "lotes":
        return {
            "encolado": False,
            "motivo": "lotes",
            "mensaje": "Este se dispara desde la pantalla Lotes: subí el Excel y la cola hace el resto.",
        }

    t = TrabajoBotRecord(
        bot_id=b.id,
        parametros=json.dumps(data.parametros, ensure_ascii=False)[:4000],
        pedido_por=current_user.email,
        progreso="En cola",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    _auditar(
        db,
        current_user.email,
        current_user.rol,
        "BOT_ENCOLADO",
        t,
        json.dumps({"bot": b.nombre, "parametros": data.parametros}, ensure_ascii=False),
    )
    return {"encolado": True, "trabajo_id": t.id, "bot": b.nombre}


@router.post("/{bot_id}/cancelar")
def cancelar_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Cancela lo abierto de ese bot (lo pendiente sale de la cola; lo
    reclamado queda marcado y el agente lo abandona al reportar)."""
    if bots_hus.obtener(bot_id) is None:
        raise HTTPException(404, f"No existe el bot '{bot_id}'")
    abiertos = (
        db.query(TrabajoBotRecord)
        .filter(
            TrabajoBotRecord.bot_id == bot_id,
            TrabajoBotRecord.estado.in_(ESTADOS_ABIERTOS),
        )
        .all()
    )
    if not abiertos:
        raise HTTPException(409, "Ese bot no tiene trabajos abiertos para cancelar")
    for t in abiertos:
        t.estado = "CANCELADO"
        t.terminado_en = datetime.now(timezone.utc)
        t.cancelado_por = current_user.email
        t.progreso = "Cancelado"
        _auditar(db, current_user.email, current_user.rol, "BOT_CANCELADO", t)
    db.commit()
    return {"ok": True, "cancelados": len(abiertos)}


@router.post("/{bot_id}/reintentar")
def reintentar_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Re-encola el último trabajo fallido o cancelado, con sus mismos
    parámetros."""
    if bots_hus.obtener(bot_id) is None:
        raise HTTPException(404, f"No existe el bot '{bot_id}'")
    ultimo = (
        db.query(TrabajoBotRecord)
        .filter(
            TrabajoBotRecord.bot_id == bot_id,
            TrabajoBotRecord.estado.in_(("ERROR", "CANCELADO")),
        )
        .order_by(TrabajoBotRecord.id.desc())
        .first()
    )
    if ultimo is None:
        raise HTTPException(409, "Ese bot no tiene un trabajo fallido o cancelado para reintentar")
    t = TrabajoBotRecord(
        bot_id=bot_id,
        parametros=ultimo.parametros,
        pedido_por=current_user.email,
        progreso=f"Reintento del trabajo #{ultimo.id}",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    _auditar(db, current_user.email, current_user.rol, "BOT_REINTENTADO", t, f"origen #{ultimo.id}")
    return {"ok": True, "trabajo_id": t.id, "reintenta_a": ultimo.id}


@router.get("/{bot_id}/historial")
def historial_bot(
    bot_id: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if bots_hus.obtener(bot_id) is None:
        raise HTTPException(404, f"No existe el bot '{bot_id}'")
    filas = (
        db.query(TrabajoBotRecord)
        .filter(TrabajoBotRecord.bot_id == bot_id)
        .order_by(TrabajoBotRecord.id.desc())
        .limit(30)
        .all()
    )
    return {"bot_id": bot_id, "trabajos": [_trabajo_dict(t) for t in filas]}
