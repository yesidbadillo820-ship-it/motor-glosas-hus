"""Endpoints del bot Telegram.

POST /telegram/webhook  — receptor de updates desde Telegram (público pero
                          protegido por secret token X-Telegram-Bot-Api-Secret-Token).
GET  /telegram/health   — ping al bot para verificar que el token funciona
                          (autenticado, sólo admin).
POST /telegram/test     — envía mensaje de prueba al usuario actual si está
                          vinculado (autenticado).
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services import telegram_service

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Receptor de updates de Telegram.

    Telegram envía POST con JSON de tipo Update. Validamos el header
    secreto que Telegram añade si lo configuramos al setear el webhook,
    para que terceros no puedan spamear este endpoint.
    """
    secret_esperado = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if secret_esperado:
        recibido = request.headers.get("x-telegram-bot-api-secret-token") or ""
        if recibido != secret_esperado:
            logger.warning(f"[TELEGRAM] webhook con secret invalido: {recibido[:10]}...")
            raise HTTPException(status_code=403, detail="forbidden")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    try:
        result = await telegram_service.procesar_update(update, db)
        return result
    except Exception as e:
        # NUNCA devolver 5xx a Telegram — sus webhooks reintentan, generando
        # spam de logs. Si algo falla, log + devolver ok para que no reintente.
        logger.error(f"[TELEGRAM] procesar_update falló: {e}", exc_info=True)
        return {"ok": True, "error_silenciado": str(e)[:200]}


@router.get("/health")
async def health(current_user: UsuarioRecord = Depends(get_usuario_actual)):
    """Verifica que el bot token sea válido. Solo autenticados."""
    return await telegram_service.health_check()


@router.post("/test")
async def test(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
    db: Session = Depends(get_db),
):
    """Envía un mensaje de prueba al chat_id vinculado al usuario actual."""
    u = db.query(UsuarioRecord).filter(UsuarioRecord.id == current_user.id).first()
    if not u or not u.telegram_chat_id:
        return {
            "ok": False,
            "error": "Tu cuenta no está vinculada a Telegram. Escribí /start tu-email al bot.",
        }
    ok = await telegram_service.enviar_mensaje(
        u.telegram_chat_id,
        f"✅ <b>Mensaje de prueba</b>\n\n"
        f"Si lo recibes, tu cuenta está bien vinculada.\n"
        f"Saludos desde el Motor Glosas HUS — {u.nombre or u.email}.",
    )
    return {"ok": ok, "chat_id_prefijo": u.telegram_chat_id[:6] + "..."}
