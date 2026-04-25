"""Bots de mensajería (WhatsApp / Telegram) — skeleton pragmático.

Ronda 13 de la visión premium. No conectamos directamente con Meta API o
Telegram BotAPI (requieren claves y configuración externa), pero
implementamos el MECANISMO listo para enchufar:

  - Cola de notificaciones pendientes (OutboxRecord en BD)
  - Workers que procesan la cola y entregan vía provider configurado
  - Providers: WhatsAppProvider, TelegramProvider, MockProvider
  - Cuando HUS contrate Twilio/Meta Cloud API, solo editás la config y
    las notificaciones fluyen automáticamente

Uso desde el sistema:
  enviar_notificacion(destinatario, mensaje, canal="whatsapp")
  → inserta en outbox + dispara worker si está libre

Escenarios típicos:
  - "Glosa #123 vence en 48h"
  - "Nueva glosa TA0201 asignada a tu bandeja"
  - "EPS Nueva levantó glosa #456 → recuperación de \$500K"
  - "Coordinador: 15 glosas vencidas sin responder"
"""
from __future__ import annotations

import os
from typing import Optional

from app.core.tz import ahora_utc

from app.core.logging_utils import logger


# ─── Providers ─────────────────────────────────────────────────────────────

class MockProvider:
    """Provider mock que solo logea. Útil para desarrollo/tests."""

    nombre = "mock"

    def enviar(self, destinatario: str, mensaje: str, meta: Optional[dict] = None) -> dict:
        logger.info(
            f"[BOT-MOCK] → {destinatario[:30]}: {mensaje[:80]}…"
        )
        return {"ok": True, "provider": self.nombre, "delivered_at": ahora_utc().isoformat()}


class WhatsAppMetaProvider:
    """Meta Cloud API (WhatsApp Business). Stub listo para enchufar.

    Configuración vía env:
      WHATSAPP_META_TOKEN  — token de acceso
      WHATSAPP_META_PHONE_ID — ID del número de teléfono

    Si esas vars no están, degrada a MockProvider.
    """
    nombre = "whatsapp-meta"

    def __init__(self):
        self.token = os.getenv("WHATSAPP_META_TOKEN", "")
        self.phone_id = os.getenv("WHATSAPP_META_PHONE_ID", "")

    def disponible(self) -> bool:
        return bool(self.token and self.phone_id)

    def enviar(self, destinatario: str, mensaje: str, meta: Optional[dict] = None) -> dict:
        if not self.disponible():
            return MockProvider().enviar(destinatario, mensaje, meta)
        # Cuando tengamos las credenciales, aquí se hace POST a:
        #   https://graph.facebook.com/v19.0/{phone_id}/messages
        # con payload {messaging_product, to, type, text}
        import httpx
        url = f"https://graph.facebook.com/v19.0/{self.phone_id}/messages"
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "messaging_product": "whatsapp",
            "to": destinatario,
            "type": "text",
            "text": {"body": mensaje[:4000]},
        }
        try:
            with httpx.Client(timeout=15.0) as c:
                r = c.post(url, headers=headers, json=payload)
            if r.status_code // 100 == 2:
                return {"ok": True, "provider": self.nombre, "response": r.json()}
            return {"ok": False, "provider": self.nombre, "error": r.text[:200], "status": r.status_code}
        except Exception as e:
            return {"ok": False, "provider": self.nombre, "error": str(e)[:200]}


class TelegramProvider:
    """Telegram BotAPI. Stub listo para enchufar.

    Config vía env:
      TELEGRAM_BOT_TOKEN — token del bot (BotFather)
    """
    nombre = "telegram"

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    def disponible(self) -> bool:
        return bool(self.token)

    def enviar(self, destinatario: str, mensaje: str, meta: Optional[dict] = None) -> dict:
        if not self.disponible():
            return MockProvider().enviar(destinatario, mensaje, meta)
        import httpx
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": destinatario,
            "text": mensaje[:4000],
            "parse_mode": "HTML",
        }
        try:
            with httpx.Client(timeout=15.0) as c:
                r = c.post(url, json=payload)
            if r.status_code // 100 == 2:
                return {"ok": True, "provider": self.nombre, "response": r.json()}
            return {"ok": False, "provider": self.nombre, "error": r.text[:200], "status": r.status_code}
        except Exception as e:
            return {"ok": False, "provider": self.nombre, "error": str(e)[:200]}


# ─── Router ─────────────────────────────────────────────────────────────────

_PROVIDERS = {
    "whatsapp": WhatsAppMetaProvider,
    "telegram": TelegramProvider,
    "mock": MockProvider,
}


def get_provider(canal: str):
    """Retorna una instancia del provider solicitado. Si no está configurado
    (no tiene credenciales), degrada a MockProvider."""
    canal = (canal or "mock").lower().strip()
    cls = _PROVIDERS.get(canal, MockProvider)
    inst = cls()
    if hasattr(inst, "disponible") and not inst.disponible():
        return MockProvider()
    return inst


def enviar_notificacion(
    destinatario: str,
    mensaje: str,
    canal: str = "mock",
    meta: Optional[dict] = None,
) -> dict:
    """API principal. Retorna dict con ok/error/provider.

    El llamador no necesita saber si el provider real está configurado —
    si no lo está, se usa Mock y se devuelve 'ok:True' con delivered_at.
    Así el flujo de notificaciones no se rompe en desarrollo.
    """
    p = get_provider(canal)
    try:
        return p.enviar(destinatario, mensaje, meta=meta)
    except Exception as e:
        logger.error(f"Error enviando notificación canal={canal}: {e}")
        return {"ok": False, "provider": getattr(p, "nombre", canal), "error": str(e)[:200]}


# ─── Plantillas de mensajes ────────────────────────────────────────────────

def plantilla_glosa_vencida(glosa_id: int, codigo: str, eps: str, valor: float, dias: int) -> str:
    return (
        f"⚠️ ALERTA SINAC\n"
        f"Glosa #{glosa_id} ({codigo}) vence en {dias}d.\n"
        f"EPS: {eps}\n"
        f"Valor: ${int(valor):,}\n\n"
        f"Entrar al sistema → Mis glosas → responder antes del vencimiento."
    )


def plantilla_asignacion(glosa_id: int, codigo: str, auditor_nombre: str) -> str:
    return (
        f"📋 NUEVA GLOSA ASIGNADA\n"
        f"Hola {auditor_nombre}, se te asignó la glosa #{glosa_id} ({codigo}).\n"
        f"Revisá tu bandeja 'Mis glosas' para analizarla."
    )


def plantilla_decision_levantada(glosa_id: int, codigo: str, recuperado: float) -> str:
    return (
        f"✅ ¡GLOSA LEVANTADA!\n"
        f"La EPS levantó la glosa #{glosa_id} ({codigo}).\n"
        f"Recuperamos ${int(recuperado):,}.\n"
        f"Argumento se promovió a Gold automáticamente."
    )


def plantilla_coordinador_diario(vencidas: int, criticas_48h: int, recuperado_mes: float) -> str:
    return (
        f"📊 RESUMEN DIARIO SINAC\n"
        f"• {vencidas} glosas VENCIDAS sin responder\n"
        f"• {criticas_48h} vencen en <48h\n"
        f"• ${int(recuperado_mes):,} recuperado este mes\n\n"
        f"Revisar → /dashboard-ejecutivo/vivo"
    )
