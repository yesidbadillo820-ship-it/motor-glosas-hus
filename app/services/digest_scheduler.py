"""Scheduler del digest ejecutivo (Ronda 20).

Dispara automáticamente el digest del día a las `DIGEST_HORA` (default 7:30)
y lo envía a los destinatarios configurados vía bot_mensajeria.

Configuración (env vars):
  DIGEST_HORA            Hora local de envío (0-23). Default 7.
  DIGEST_MINUTO          Minuto (0-59). Default 30.
  DIGEST_CANAL           whatsapp | telegram | mock. Default mock.
  DIGEST_DESTINATARIOS   Lista separada por coma: "+57300...,+57301..."
                          o chat_ids de Telegram. Si está vacía, el loop
                          no corre (apagado por config).
  DIGEST_PERIODO         dia | semana | mes. Default dia.

Patrón idéntico al de ia_auditora_proactiva (Ronda 2): asyncio.Task en
background dentro del mismo proceso FastAPI, sin cron externo. Resistente
a excepciones.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

from app.core.logging_utils import logger
from app.database import SessionLocal
from app.services.bot_mensajeria import enviar_notificacion
from app.services.digest_ejecutivo import (
    formatear_digest_texto,
    generar_digest,
)


_SCHEDULER_TASK: Optional[asyncio.Task] = None
_ULTIMA_EJECUCION: Optional[datetime] = None
_EJECUCION_EN_CURSO: bool = False


def _config() -> dict:
    """Lee la config del entorno. Se lee on-demand (no cache) para que el
    usuario pueda cambiarla sin reiniciar si usa /digest/enviar manual."""
    return {
        "hora": int(os.getenv("DIGEST_HORA", "7")),
        "minuto": int(os.getenv("DIGEST_MINUTO", "30")),
        "canal": os.getenv("DIGEST_CANAL", "mock").strip().lower(),
        "destinatarios": [
            d.strip()
            for d in (os.getenv("DIGEST_DESTINATARIOS", "") or "").split(",")
            if d.strip()
        ],
        "periodo": os.getenv("DIGEST_PERIODO", "dia").strip().lower(),
    }


def _segundos_hasta_proximo_envio() -> float:
    """Segundos desde ahora hasta la próxima `hora:minuto` configurada."""
    cfg = _config()
    ahora = datetime.now()
    objetivo = ahora.replace(
        hour=max(0, min(23, cfg["hora"])),
        minute=max(0, min(59, cfg["minuto"])),
        second=0,
        microsecond=0,
    )
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    return (objetivo - ahora).total_seconds()


async def _loop_digest():
    """Loop infinito que envía el digest una vez por día.

    Si DIGEST_DESTINATARIOS está vacío, el loop se suicida inmediatamente
    (no tiene sentido correr sin quién recibir)."""
    cfg = _config()
    if not cfg["destinatarios"]:
        logger.info("[DIGEST] Apagado — DIGEST_DESTINATARIOS vacío.")
        return

    while True:
        try:
            espera_s = _segundos_hasta_proximo_envio()
            horas = espera_s / 3600
            logger.info(f"[DIGEST] Próximo envío en {horas:.1f}h")
            await asyncio.sleep(espera_s)
            await ejecutar_envio_digest()
        except asyncio.CancelledError:
            logger.info("[DIGEST] Scheduler cancelado (shutdown)")
            break
        except Exception as e:
            logger.error(f"[DIGEST] Error en loop: {e}. Reintentando en 1h.")
            await asyncio.sleep(3600)


async def ejecutar_envio_digest() -> dict:
    """Genera el digest y lo envía a cada destinatario. Serializado.

    Devuelve stats: {procesados, enviados_ok, errores}.
    """
    global _ULTIMA_EJECUCION, _EJECUCION_EN_CURSO
    if _EJECUCION_EN_CURSO:
        return {"skip": "ya hay ejecución en curso"}
    _EJECUCION_EN_CURSO = True
    try:
        cfg = _config()
        if not cfg["destinatarios"]:
            return {"skip": "sin destinatarios"}
        db = SessionLocal()
        try:
            digest = generar_digest(db, periodo=cfg["periodo"])
            texto = formatear_digest_texto(digest)
        finally:
            db.close()

        ok = 0
        errores = []
        for dest in cfg["destinatarios"]:
            try:
                r = enviar_notificacion(destinatario=dest, mensaje=texto, canal=cfg["canal"])
                if r.get("ok"):
                    ok += 1
                else:
                    errores.append({"dest": dest, "error": r.get("error")})
            except Exception as e:
                errores.append({"dest": dest, "error": str(e)[:120]})

        _ULTIMA_EJECUCION = datetime.now()
        stats = {
            "procesados": len(cfg["destinatarios"]),
            "enviados_ok": ok,
            "errores": errores,
            "canal": cfg["canal"],
            "periodo": cfg["periodo"],
            "timestamp": _ULTIMA_EJECUCION.isoformat(),
        }
        logger.info(f"[DIGEST] Envío completado: {stats}")
        return stats
    finally:
        _EJECUCION_EN_CURSO = False


def iniciar_scheduler() -> None:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return
    cfg = _config()
    if not cfg["destinatarios"]:
        logger.info("[DIGEST] Scheduler NO iniciado — DIGEST_DESTINATARIOS vacío.")
        return
    try:
        loop = asyncio.get_event_loop()
        _SCHEDULER_TASK = loop.create_task(_loop_digest())
        logger.info(
            f"[DIGEST] Scheduler iniciado — {cfg['hora']:02d}:{cfg['minuto']:02d} "
            f"via {cfg['canal']} a {len(cfg['destinatarios'])} destinatario(s)"
        )
    except Exception as e:
        logger.warning(f"[DIGEST] No se pudo iniciar scheduler: {e}")


def detener_scheduler() -> None:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        _SCHEDULER_TASK.cancel()
    _SCHEDULER_TASK = None


def obtener_estado() -> dict:
    cfg = _config()
    return {
        "scheduler_activo": bool(_SCHEDULER_TASK and not _SCHEDULER_TASK.done()),
        "ejecucion_en_curso": _EJECUCION_EN_CURSO,
        "ultima_ejecucion": _ULTIMA_EJECUCION.isoformat() if _ULTIMA_EJECUCION else None,
        "config": {
            "hora": cfg["hora"],
            "minuto": cfg["minuto"],
            "canal": cfg["canal"],
            "periodo": cfg["periodo"],
            "destinatarios_configurados": len(cfg["destinatarios"]),
        },
    }
