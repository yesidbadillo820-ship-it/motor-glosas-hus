"""Webhooks salientes configurables.

Cuando ocurre un evento cuyo nombre coincide con `eventos` (CSV) de
un webhook activo, el sistema envia POST async al url con el payload
del evento. Util para integrar con Slack/Teams/n8n/Zapier.

CRUD restringido a COORDINADOR/SUPER_ADMIN. Disparo via funcion
`disparar_webhooks_para_evento(db, accion, payload)` que se llama
desde otros endpoints o background tasks.
"""
from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import get_coordinador_o_admin, get_usuario_actual
from app.core.tz import ahora_utc
from app.database import SessionLocal, get_db
from app.models.db import UsuarioRecord, WebhookRecord


router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("motor_glosas")


class WebhookInput(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=8, max_length=800)
    secret: str | None = Field(None, max_length=64)
    eventos: str = Field(..., min_length=2)  # CSV
    activo: bool = True


def _serializar(w: WebhookRecord) -> dict:
    return {
        "id": w.id,
        "nombre": w.nombre,
        "url": w.url,
        "tiene_secret": bool(w.secret),
        "eventos": w.eventos,
        "activo": bool(w.activo),
        "creado_en": w.creado_en.isoformat() if w.creado_en else None,
        "ultimo_disparo": w.ultimo_disparo.isoformat() if w.ultimo_disparo else None,
        "ultimo_status": w.ultimo_status,
        "disparos_total": w.disparos_total,
        "disparos_fallidos": w.disparos_fallidos,
    }


@router.get("")
def listar(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    rows = db.query(WebhookRecord).order_by(WebhookRecord.id.desc()).all()
    return [_serializar(w) for w in rows]


@router.post("")
def crear(
    data: WebhookInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    if not data.url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL invalida (debe empezar con http:// o https://)")
    w = WebhookRecord(
        nombre=data.nombre[:100],
        url=data.url[:800],
        secret=(data.secret or "").strip()[:64] or None,
        eventos=data.eventos[:500],
        activo=1 if data.activo else 0,
        creado_por=current_user.email,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return _serializar(w)


@router.put("/{webhook_id}")
def actualizar(
    webhook_id: int,
    data: WebhookInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    w = db.query(WebhookRecord).filter(WebhookRecord.id == webhook_id).first()
    if not w:
        raise HTTPException(404, "No encontrado")
    w.nombre = data.nombre[:100]
    w.url = data.url[:800]
    if data.secret is not None:
        w.secret = data.secret.strip()[:64] or None
    w.eventos = data.eventos[:500]
    w.activo = 1 if data.activo else 0
    db.commit()
    return _serializar(w)


@router.delete("/{webhook_id}")
def borrar(
    webhook_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    w = db.query(WebhookRecord).filter(WebhookRecord.id == webhook_id).first()
    if not w:
        raise HTTPException(404, "No encontrado")
    db.delete(w)
    db.commit()
    return {"ok": True, "id": webhook_id}


@router.post("/{webhook_id}/test")
async def probar(
    webhook_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    w = db.query(WebhookRecord).filter(WebhookRecord.id == webhook_id).first()
    if not w:
        raise HTTPException(404, "No encontrado")
    payload = {
        "event": "WEBHOOK_TEST",
        "timestamp": ahora_utc().isoformat(),
        "data": {"hello": "from-motor-glosas-hus", "user": current_user.email},
    }
    background.add_task(_disparar_uno, w.id, payload)
    return {"ok": True, "queued": True}


async def _disparar_uno(webhook_id: int, payload: dict):
    """Tarea background que dispara un webhook individual."""
    db = SessionLocal()
    try:
        w = db.query(WebhookRecord).filter(WebhookRecord.id == webhook_id).first()
        if not w or not w.activo:
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "motor-glosas-hus/1.0"}
        if w.secret:
            sig = hmac.new(w.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers["X-Motor-Signature"] = "sha256=" + sig
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                r = await client.post(w.url, content=body, headers=headers)
            w.ultimo_status = str(r.status_code)
            w.disparos_total = (w.disparos_total or 0) + 1
            if r.status_code >= 400:
                w.disparos_fallidos = (w.disparos_fallidos or 0) + 1
                logger.warning(f"Webhook {w.id} ({w.nombre}) HTTP {r.status_code}")
        except Exception as e:
            w.ultimo_status = "error"
            w.disparos_total = (w.disparos_total or 0) + 1
            w.disparos_fallidos = (w.disparos_fallidos or 0) + 1
            logger.warning(f"Webhook {w.id} ({w.nombre}) fallo: {e}")
        w.ultimo_disparo = ahora_utc()
        db.commit()
    except Exception as e:
        logger.error(f"_disparar_uno error: {e}")
    finally:
        db.close()


def disparar_webhooks_para_evento(db: Session, accion: str, payload: dict):
    """API publica: invocar desde cualquier endpoint cuando ocurra un
    evento que pueda interesar a webhooks suscritos. Encola los
    disparos en asyncio.create_task (no bloqueante).

    Ejemplo: disparar_webhooks_para_evento(db, "DECISION_EPS",
        {"glosa_id": 123, "decision": "LEVANTADA", ...})
    """
    try:
        rows = (
            db.query(WebhookRecord)
            .filter(WebhookRecord.activo == 1)
            .all()
        )
        suscritos = []
        for w in rows:
            eventos_set = {e.strip().upper() for e in (w.eventos or "").split(",") if e.strip()}
            if "*" in eventos_set or accion.upper() in eventos_set:
                suscritos.append(w.id)
        if not suscritos:
            return
        full_payload = {
            "event": accion,
            "timestamp": ahora_utc().isoformat(),
            "data": payload,
        }
        try:
            loop = asyncio.get_event_loop()
            for wid in suscritos:
                loop.create_task(_disparar_uno(wid, full_payload))
        except RuntimeError:
            # No hay loop activo (worker sync) - usar threading fallback
            import threading
            for wid in suscritos:
                t = threading.Thread(target=lambda: asyncio.run(_disparar_uno(wid, full_payload)), daemon=True)
                t.start()
    except Exception as e:
        logger.warning(f"disparar_webhooks_para_evento error: {e}")
