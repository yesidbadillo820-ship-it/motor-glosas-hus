"""Monitor de salud del sistema (Ronda 17).

Un único endpoint que responde la pregunta del gestor cada mañana:
«¿todo está funcionando okay?». Consolida varias señales:

  - BD: ping + latencia query simple
  - Scheduler pre-análisis (IA proactiva): último run + próximo run
  - Caché IA: tamaño actual + hit_count acumulado (ahorro)
  - Glosas del día: radicadas, respondidas, pendientes, vencidas
  - Anomalías: duplicados + patrones EPS sin revisar
  - Bots de mensajería: providers configurados (WhatsApp/Telegram/mock)
  - Actividad reciente (últimas 6 h de audit_log)

Formato respuesta:
  {
    "estado_general": "OK" | "ATENCION" | "CRITICO",
    "generado_en": iso8601,
    "componentes": {
      "bd": {"estado", "latencia_ms", "detalle"},
      "scheduler_ia_proactiva": {...},
      "cache_ia": {...},
      "glosas_hoy": {...},
      "anomalias": {...},
      "bots": {...},
      "actividad_reciente": {...},
    },
    "alertas": [{"nivel", "mensaje"}],
  }

El campo `estado_general` se calcula así:
  - CRITICO  → BD caída o ≥10 glosas vencidas o ≥3 alertas ALTA en anomalías
  - ATENCION → scheduler inactivo +24h o ≥1 glosa vencida o ≥1 alerta MEDIA
  - OK       → nada de lo anterior
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.db import (
    AICacheRecord,
    AuditLogRecord,
    GlosaRecord,
)
from app.services.detector_anomalias import (
    detectar_duplicados,
    detectar_patron_sospechoso_eps,
)


# ─── Helpers de componentes individuales ───────────────────────────────────

def _check_bd(db: Session) -> dict:
    """Ping a la BD con una query trivial. Mide latencia."""
    t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        lat = (time.perf_counter() - t0) * 1000
        estado = "OK" if lat < 500 else "LENTO"
        return {
            "estado": estado,
            "latencia_ms": round(lat, 1),
            "detalle": "ping OK" if estado == "OK" else f"latencia {lat:.0f}ms > 500ms",
        }
    except Exception as e:
        return {
            "estado": "CRITICO",
            "latencia_ms": None,
            "detalle": f"error: {str(e)[:120]}",
        }


def _check_scheduler() -> dict:
    try:
        from app.services.ia_auditora_proactiva import obtener_estado
        est = obtener_estado()
    except Exception as e:
        return {"estado": "DESCONOCIDO", "detalle": str(e)[:120]}

    activo = bool(est.get("scheduler_activo"))
    ultima = est.get("ultima_ejecucion")
    estado = "OK" if activo else "INACTIVO"
    return {
        "estado": estado,
        "activo": activo,
        "ejecucion_en_curso": bool(est.get("ejecucion_en_curso")),
        "ultima_ejecucion": ultima,
        "detalle": "scheduler corriendo" if activo else "scheduler apagado",
    }


def _check_cache_ia(db: Session) -> dict:
    try:
        total = db.query(func.count(AICacheRecord.id)).scalar() or 0
        hits = db.query(func.coalesce(func.sum(AICacheRecord.hit_count), 0)).scalar() or 0
        return {
            "estado": "OK",
            "entradas": int(total),
            "hits_acumulados": int(hits),
            "ratio_ahorro": (
                round(float(hits) / max(1, float(total) + float(hits)), 3)
                if (total or hits) else 0.0
            ),
        }
    except Exception as e:
        return {"estado": "DESCONOCIDO", "detalle": str(e)[:120]}


def _check_glosas_hoy(db: Session) -> dict:
    ahora = datetime.now(timezone.utc)
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        radicadas_hoy = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.creado_en >= inicio_hoy)
            .scalar() or 0
        )
        vencidas = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.estado == "PENDIENTE")
            .filter(GlosaRecord.dias_restantes < 0)
            .scalar() or 0
        )
        pendientes = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.estado == "PENDIENTE")
            .scalar() or 0
        )
        respondidas_hoy = (
            db.query(func.count(GlosaRecord.id))
            .filter(GlosaRecord.fecha_decision_eps >= inicio_hoy)
            .scalar() or 0
        )
        if vencidas >= 10:
            estado = "CRITICO"
        elif vencidas >= 1:
            estado = "ATENCION"
        else:
            estado = "OK"
        return {
            "estado": estado,
            "radicadas_hoy": int(radicadas_hoy),
            "respondidas_hoy": int(respondidas_hoy),
            "pendientes_total": int(pendientes),
            "vencidas": int(vencidas),
        }
    except Exception as e:
        return {"estado": "DESCONOCIDO", "detalle": str(e)[:120]}


def _check_anomalias(db: Session) -> dict:
    try:
        dup = detectar_duplicados(db, ventana_dias=30)
        patr = detectar_patron_sospechoso_eps(db, ventana_dias=30)
        alta = sum(1 for a in dup + patr if a.severidad == "ALTA")
        media = sum(1 for a in dup + patr if a.severidad == "MEDIA")
        if alta >= 3:
            estado = "CRITICO"
        elif alta >= 1 or media >= 3:
            estado = "ATENCION"
        else:
            estado = "OK"
        return {
            "estado": estado,
            "duplicados": len(dup),
            "patrones_eps": len(patr),
            "alta": alta,
            "media": media,
        }
    except Exception as e:
        return {"estado": "DESCONOCIDO", "detalle": str(e)[:120]}


def _check_bots() -> dict:
    try:
        from app.services.bot_mensajeria import (
            WhatsAppMetaProvider,
            TelegramProvider,
        )
        wa = WhatsAppMetaProvider()
        tg = TelegramProvider()
        configurados = []
        if wa.disponible():
            configurados.append("whatsapp-meta")
        if tg.disponible():
            configurados.append("telegram")
        return {
            "estado": "OK",
            "providers_configurados": configurados,
            "fallback_activo": "mock" if not configurados else None,
        }
    except Exception as e:
        return {"estado": "DESCONOCIDO", "detalle": str(e)[:120]}


def _check_actividad_reciente(db: Session, horas: int = 6) -> dict:
    desde = datetime.now(timezone.utc) - timedelta(hours=horas)
    try:
        total = (
            db.query(func.count(AuditLogRecord.id))
            .filter(AuditLogRecord.timestamp >= desde)
            .scalar() or 0
        )
        usuarios_activos = (
            db.query(func.count(func.distinct(AuditLogRecord.usuario_email)))
            .filter(AuditLogRecord.timestamp >= desde)
            .scalar() or 0
        )
        return {
            "estado": "OK",
            "ventana_horas": horas,
            "eventos": int(total),
            "usuarios_activos": int(usuarios_activos),
        }
    except Exception as e:
        return {"estado": "DESCONOCIDO", "detalle": str(e)[:120]}


# ─── Orquestador ───────────────────────────────────────────────────────────

def _peor_estado(estados: list[str]) -> str:
    """Regresa el peor estado del conjunto."""
    prioridad = {
        "CRITICO": 4,
        "ATENCION": 3,
        "LENTO": 2,
        "INACTIVO": 2,
        "DESCONOCIDO": 1,
        "OK": 0,
    }
    if not estados:
        return "OK"
    peor = max(estados, key=lambda e: prioridad.get(e, 0))
    if peor in ("CRITICO",):
        return "CRITICO"
    if peor in ("ATENCION", "LENTO", "INACTIVO"):
        return "ATENCION"
    if peor in ("DESCONOCIDO",):
        return "ATENCION"
    return "OK"


def checar_salud(db: Session) -> dict[str, Any]:
    """Consolida todos los componentes en un único reporte."""
    componentes = {
        "bd": _check_bd(db),
        "scheduler_ia_proactiva": _check_scheduler(),
        "cache_ia": _check_cache_ia(db),
        "glosas_hoy": _check_glosas_hoy(db),
        "anomalias": _check_anomalias(db),
        "bots": _check_bots(),
        "actividad_reciente": _check_actividad_reciente(db),
    }
    estados = [c.get("estado", "OK") for c in componentes.values()]
    general = _peor_estado(estados)

    alertas = []
    if componentes["bd"]["estado"] == "CRITICO":
        alertas.append({"nivel": "CRITICO", "mensaje": "Base de datos sin respuesta."})
    if componentes["glosas_hoy"].get("vencidas", 0) >= 1:
        alertas.append({
            "nivel": "ATENCION" if componentes["glosas_hoy"]["vencidas"] < 10 else "CRITICO",
            "mensaje": f"{componentes['glosas_hoy']['vencidas']} glosas vencidas sin responder.",
        })
    if componentes["anomalias"].get("alta", 0) >= 1:
        alertas.append({
            "nivel": "ATENCION",
            "mensaje": f"{componentes['anomalias']['alta']} anomalías críticas detectadas.",
        })
    if not componentes["scheduler_ia_proactiva"].get("activo"):
        alertas.append({
            "nivel": "ATENCION",
            "mensaje": "Scheduler de IA proactiva inactivo.",
        })

    return {
        "estado_general": general,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "componentes": componentes,
        "alertas": alertas,
        "entorno": {
            "env": os.getenv("ENV", "dev"),
            "version": os.getenv("APP_VERSION", "unknown"),
        },
    }
