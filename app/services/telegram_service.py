"""Bot Telegram para alertas push a los gestores.

Diseño:
  • El bot vive en el mismo proceso FastAPI; no hay daemon separado.
    Usamos el webhook que Telegram expone (POST /telegram/webhook)
    para procesar comandos del usuario (`/start`, `/parar`, `/preferencias`).
  • El bot envía alertas vía la API HTTP de Telegram (POST a
    https://api.telegram.org/bot<TOKEN>/sendMessage). Sin librería
    externa — httpx directo.
  • Si TELEGRAM_BOT_TOKEN no está configurado, todas las funciones
    quedan en no-op. El proyecto sigue funcionando.

Setup en producción:
  1. Chatear con @BotFather en Telegram → /newbot → recibir token.
  2. fly secrets set TELEGRAM_BOT_TOKEN=123456:abc... -a motor-glosas-hus
  3. (Opcional) fly secrets set TELEGRAM_WEBHOOK_SECRET=<random_32_chars>
     para que solo Telegram pueda llamar nuestro endpoint /telegram/webhook.
  4. Setear el webhook (1 vez):
        curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
          -d "url=https://motor-glosas-hus.fly.dev/telegram/webhook" \
          -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
  5. Gestor abre el bot en Telegram → /start <email>  → queda vinculado.

Eventos que disparan alertas (futuros, configurables):
  • Glosa nueva ROJA/NEGRA asignada a este gestor.
  • Glosa vence en <24h (resumen diario a las 8:00 -05).
  • Auto-responder terminó tu lote: N respondidas / M manual.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("motor_glosas")


_TELEGRAM_API_BASE = "https://api.telegram.org"
_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


def _bot_token() -> str:
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


def disponible() -> bool:
    return bool(_bot_token())


async def enviar_mensaje(
    chat_id: str,
    texto: str,
    parse_mode: str = "HTML",
    disable_preview: bool = True,
    reply_markup: Optional[dict] = None,
) -> bool:
    """Envía un mensaje a un chat. Retorna True si Telegram respondió 200.

    texto soporta HTML básico: <b>, <i>, <code>, <pre>, <a href="">.
    No subir links a documentos con PHI — usar IDs internos.
    """
    token = _bot_token()
    if not token:
        return False
    if not chat_id:
        return False

    url = f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload: dict = {
        "chat_id": chat_id,
        "text": texto[:4000],  # límite duro de Telegram: 4096 chars
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(url, json=payload)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok"):
                return True
            logger.warning(
                f"[TELEGRAM] sendMessage ok=false: {data.get('description', '?')}"
            )
            return False
        # 403 = bot bloqueado por el usuario; 400 = chat_id inválido
        logger.warning(
            f"[TELEGRAM] sendMessage HTTP {r.status_code}: {r.text[:200]}"
        )
        return False
    except Exception as e:
        logger.warning(f"[TELEGRAM] sendMessage falló: {e}")
        return False


async def enviar_a_email(email: str, texto: str, db=None) -> bool:
    """Busca el UsuarioRecord por email y envía el mensaje a su
    telegram_chat_id. Si no tiene chat_id vinculado, retorna False
    silenciosamente (no es error)."""
    if not email:
        return False
    cerrar_db = False
    try:
        if db is None:
            from app.database import SessionLocal
            db = SessionLocal()
            cerrar_db = True
        from app.models.db import UsuarioRecord
        u = db.query(UsuarioRecord).filter(
            UsuarioRecord.email == email.lower().strip(),
            UsuarioRecord.activo == 1,
        ).first()
        if not u or not u.telegram_chat_id:
            return False
        return await enviar_mensaje(u.telegram_chat_id, texto)
    except Exception as e:
        logger.warning(f"[TELEGRAM] enviar_a_email({email}) falló: {e}")
        return False
    finally:
        if cerrar_db and db is not None:
            db.close()


# ──────────────────────────────────────────────────────────────────────
# Webhook handler — procesa comandos del usuario
# ──────────────────────────────────────────────────────────────────────

_PREFERENCIAS_DEFAULT = "rojas,negras,resumen_diario,vence_hoy"


async def procesar_update(update: dict, db) -> dict:
    """Procesa un Update de Telegram. Maneja /start, /parar,
    /preferencias, /estado. Retorna respuesta para diagnóstico.

    Comando esperado para vincular:
      /start usuario@hus.gov.co
    El bot busca ese email en UsuarioRecord y guarda chat_id si match.
    """
    msg = update.get("message") or update.get("edited_message") or {}
    if not msg:
        return {"ok": True, "skip": "no message"}

    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return {"ok": True, "skip": "no text or chat_id"}

    from app.models.db import UsuarioRecord

    if text.startswith("/start"):
        partes = text.split(maxsplit=1)
        if len(partes) == 1:
            await enviar_mensaje(chat_id, (
                "👋 <b>Hola, soy el bot del Motor Glosas HUS.</b>\n\n"
                "Para vincular tu cuenta, escribime:\n"
                "<code>/start tu-email@hus.gov.co</code>\n\n"
                "Después recibirás alertas de glosas urgentes asignadas a ti."
            ))
            return {"ok": True, "accion": "saludo"}
        email = partes[1].strip().lower()
        u = db.query(UsuarioRecord).filter(
            UsuarioRecord.email == email,
            UsuarioRecord.activo == 1,
        ).first()
        if not u:
            await enviar_mensaje(chat_id, (
                f"❌ No encontré una cuenta activa con el email "
                f"<code>{email}</code>. Verifica con el coordinador "
                f"que tu usuario esté creado y activo en la app."
            ))
            return {"ok": True, "accion": "email_no_encontrado", "email": email}

        u.telegram_chat_id = chat_id
        if not u.telegram_preferencias:
            u.telegram_preferencias = _PREFERENCIAS_DEFAULT
        db.commit()

        await enviar_mensaje(chat_id, (
            f"✅ <b>¡Listo, {u.nombre or email}!</b>\n\n"
            f"Tu cuenta quedó vinculada. Recibirás alertas de:\n"
            f"• Glosas <b>ROJAS</b> (vencen en &lt;5 días)\n"
            f"• Glosas <b>NEGRAS</b> (ya vencidas)\n"
            f"• Resumen diario a las 8:00 AM\n"
            f"• Aviso cuando una glosa tuya vence hoy\n\n"
            f"Comandos disponibles:\n"
            f"<code>/preferencias</code> — ver/cambiar qué alertas recibes\n"
            f"<code>/parar</code> — desvincular tu cuenta\n"
            f"<code>/estado</code> — ver glosas pendientes ahora mismo"
        ))
        return {"ok": True, "accion": "vinculado", "email": email, "chat_id": chat_id}

    if text.startswith("/parar") or text.startswith("/stop"):
        u = db.query(UsuarioRecord).filter(
            UsuarioRecord.telegram_chat_id == chat_id,
            UsuarioRecord.activo == 1,
        ).first()
        if u:
            u.telegram_chat_id = None
            db.commit()
            await enviar_mensaje(chat_id, (
                "🔕 Desvinculado. No recibirás más alertas. "
                "Si querés volver a activar, escribime <code>/start tu-email@hus.gov.co</code>."
            ))
            return {"ok": True, "accion": "desvinculado"}
        await enviar_mensaje(chat_id, "ℹ️ Este chat no estaba vinculado a ninguna cuenta.")
        return {"ok": True, "accion": "ya_desvinculado"}

    if text.startswith("/preferencias"):
        u = db.query(UsuarioRecord).filter(
            UsuarioRecord.telegram_chat_id == chat_id,
            UsuarioRecord.activo == 1,
        ).first()
        if not u:
            await enviar_mensaje(chat_id, "⚠️ Primero vinculá tu cuenta con <code>/start tu-email@hus.gov.co</code>")
            return {"ok": True, "accion": "no_vinculado"}
        prefs = (u.telegram_preferencias or _PREFERENCIAS_DEFAULT).split(",")
        await enviar_mensaje(chat_id, (
            f"🔧 <b>Tus preferencias actuales:</b>\n"
            f"{', '.join(prefs) if prefs else '(ninguna)'}\n\n"
            "Para cambiar, configurá desde la app web → Perfil → Notificaciones. "
            "Pronto te dejaré cambiarlas también desde acá."
        ))
        return {"ok": True, "accion": "preferencias", "prefs": prefs}

    if text.startswith("/estado"):
        u = db.query(UsuarioRecord).filter(
            UsuarioRecord.telegram_chat_id == chat_id,
            UsuarioRecord.activo == 1,
        ).first()
        if not u:
            await enviar_mensaje(chat_id, "⚠️ Primero vinculá tu cuenta con <code>/start tu-email@hus.gov.co</code>")
            return {"ok": True, "accion": "no_vinculado"}
        from app.models.db import GlosaRecord
        rojas = db.query(GlosaRecord).filter(
            GlosaRecord.gestor == u.nombre, GlosaRecord.prioridad == "ROJO",
            GlosaRecord.workflow_state != "RADICADA",
        ).count()
        negras = db.query(GlosaRecord).filter(
            GlosaRecord.gestor == u.nombre, GlosaRecord.prioridad == "NEGRO",
            GlosaRecord.workflow_state != "RADICADA",
        ).count()
        amarillas = db.query(GlosaRecord).filter(
            GlosaRecord.gestor == u.nombre, GlosaRecord.prioridad == "AMARILLO",
            GlosaRecord.workflow_state != "RADICADA",
        ).count()
        await enviar_mensaje(chat_id, (
            f"📊 <b>Tu bandeja, {u.nombre}:</b>\n\n"
            f"⚫ Vencidas: <b>{negras}</b>\n"
            f"🔴 Críticas (&lt;5 días): <b>{rojas}</b>\n"
            f"🟡 Próximas (5-10 días): <b>{amarillas}</b>\n\n"
            f"🔗 https://motor-glosas-hus.fly.dev/"
        ))
        return {"ok": True, "accion": "estado"}

    # Cualquier otro texto → saludo
    await enviar_mensaje(chat_id, (
        "Comandos:\n"
        "<code>/start tu-email@hus.gov.co</code> — vincular cuenta\n"
        "<code>/estado</code> — ver tus glosas pendientes\n"
        "<code>/preferencias</code> — ver alertas activas\n"
        "<code>/parar</code> — desvincular"
    ))
    return {"ok": True, "accion": "desconocido"}


# ──────────────────────────────────────────────────────────────────────
# Senders de alta nivel (los usa el resto de la app)
# ──────────────────────────────────────────────────────────────────────


def _formato_valor(v: float) -> str:
    try:
        return f"${int(v):,}".replace(",", ".")
    except Exception:
        return "$?"


async def notificar_glosa_urgente(glosa, db=None) -> bool:
    """Notifica al gestor asignado a esta glosa via Telegram, si está
    vinculado y su preferencia incluye 'rojas' o 'negras'. Best-effort.
    """
    if not disponible():
        return False
    if not glosa or not glosa.gestor:
        return False
    prioridad = (glosa.prioridad or "").upper()
    if prioridad not in ("ROJO", "NEGRO"):
        return False

    cerrar_db = False
    try:
        if db is None:
            from app.database import SessionLocal
            db = SessionLocal()
            cerrar_db = True
        from app.models.db import UsuarioRecord
        u = db.query(UsuarioRecord).filter(
            UsuarioRecord.nombre == glosa.gestor,
            UsuarioRecord.activo == 1,
        ).first()
        if not u or not u.telegram_chat_id:
            return False
        prefs = (u.telegram_preferencias or _PREFERENCIAS_DEFAULT).lower()
        if prioridad == "ROJO" and "rojas" not in prefs:
            return False
        if prioridad == "NEGRO" and "negras" not in prefs:
            return False

        icono = "⚫" if prioridad == "NEGRO" else "🔴"
        msg = (
            f"{icono} <b>Glosa {prioridad}</b> asignada a vos\n\n"
            f"<b>Factura:</b> {glosa.factura or '?'}\n"
            f"<b>EPS:</b> {(glosa.eps or '?')[:60]}\n"
            f"<b>Valor:</b> {_formato_valor(glosa.valor_objetado or 0)}\n"
            f"<b>Vence:</b> {glosa.fecha_vencimiento.strftime('%d/%m/%Y') if glosa.fecha_vencimiento else '?'}\n"
            f"<b>Días restantes:</b> {glosa.dias_restantes if glosa.dias_restantes is not None else '?'}\n\n"
            f"🔗 <a href=\"https://motor-glosas-hus.fly.dev/\">Abrir en la app</a>"
        )
        return await enviar_mensaje(u.telegram_chat_id, msg)
    except Exception as e:
        logger.warning(f"[TELEGRAM] notificar_glosa_urgente falló: {e}")
        return False
    finally:
        if cerrar_db and db is not None:
            db.close()


async def enviar_resumen_diario(db) -> dict:
    """Envía a cada gestor vinculado un resumen de sus glosas pendientes.
    Pensado para correr en scheduler a las 8:00 -05.

    Retorna {enviados, sin_chat, sin_pendientes}.
    """
    if not disponible():
        return {"enviados": 0, "sin_chat": 0, "sin_pendientes": 0, "razon": "TELEGRAM_BOT_TOKEN vacío"}

    from app.models.db import UsuarioRecord, GlosaRecord
    usuarios = db.query(UsuarioRecord).filter(
        UsuarioRecord.activo == 1,
        UsuarioRecord.telegram_chat_id.isnot(None),
    ).all()
    enviados = 0
    sin_pendientes = 0
    for u in usuarios:
        prefs = (u.telegram_preferencias or _PREFERENCIAS_DEFAULT).lower()
        if "resumen_diario" not in prefs:
            continue
        rojas = db.query(GlosaRecord).filter(
            GlosaRecord.gestor == u.nombre, GlosaRecord.prioridad == "ROJO",
            GlosaRecord.workflow_state != "RADICADA",
        ).count()
        negras = db.query(GlosaRecord).filter(
            GlosaRecord.gestor == u.nombre, GlosaRecord.prioridad == "NEGRO",
            GlosaRecord.workflow_state != "RADICADA",
        ).count()
        if rojas == 0 and negras == 0:
            sin_pendientes += 1
            continue
        msg = (
            f"☀️ <b>Buenos días, {u.nombre.split()[0] if u.nombre else 'gestor'}.</b>\n\n"
            f"Tu bandeja hoy:\n"
            f"⚫ Vencidas: <b>{negras}</b>\n"
            f"🔴 Críticas (&lt;5 días): <b>{rojas}</b>\n\n"
            f"💡 Empezá por las negras antes que la EPS opere el silencio en contra.\n"
            f"🔗 https://motor-glosas-hus.fly.dev/"
        )
        if await enviar_mensaje(u.telegram_chat_id, msg):
            enviados += 1
        await asyncio.sleep(0.05)  # respetar rate-limit Telegram (~30 msg/s)

    return {
        "enviados": enviados,
        "sin_chat": 0,
        "sin_pendientes": sin_pendientes,
        "vinculados_total": len(usuarios),
    }


async def health_check() -> dict:
    """Verifica que el bot token sea válido (getMe)."""
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN no configurado"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(f"{_TELEGRAM_API_BASE}/bot{token}/getMe")
        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        data = r.json()
        if not data.get("ok"):
            return {"ok": False, "error": data.get("description", "?")}
        bot = data.get("result", {})
        return {
            "ok": True,
            "bot_username": bot.get("username"),
            "bot_id": bot.get("id"),
            "first_name": bot.get("first_name"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
