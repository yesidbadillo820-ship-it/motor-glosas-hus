"""Endpoints de health-check y diagnóstico (R51 P6).

Extraídos de app/main.py. Agrupa:
  - GET /health            → healthcheck público (status + version + banner)
  - GET /health/detail     → métricas detalladas del sistema (requiere auth)
  - GET /mi-dia            → dashboard personal del gestor (tareas + alertas + métricas)
  - GET /debug/sentry-test → test intencional de integración Sentry
"""

from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.database import SessionLocal, get_db
from app.models.db import GlosaRecord, TareaDiariaRecord, UsuarioRecord
from sqlalchemy.orm import Session

router = APIRouter(tags=["sistema"])

cfg = get_settings()

# Momento en que arrancó el proceso (aproximado).
_STARTUP_TIME = time.time()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": cfg.app_version,
        "banner": (cfg.banner_capacitacion or "").strip(),
    }


@router.get("/health/detail")
def health_detail(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Métricas detalladas del sistema. Requiere autenticación."""
    uptime_seconds = int(time.time() - _STARTUP_TIME)
    uptime_h = uptime_seconds // 3600
    uptime_m = (uptime_seconds % 3600) // 60

    # Estadísticas de la base de datos
    db_stats: dict = {}
    try:
        with SessionLocal() as db:
            total_glosas = db.query(GlosaRecord).count()
            total_usuarios = db.query(UsuarioRecord).count()
            db_stats = {
                "total_glosas": total_glosas,
                "total_usuarios": total_usuarios,
                "engine": "SQLite" if "sqlite" in cfg.database_url else "PostgreSQL",
            }
    except Exception as exc:
        db_stats = {"error": str(exc)}

    # Métricas de sistema (psutil opcional)
    sys_stats: dict = {}
    try:
        import psutil  # type: ignore[import]

        proc = psutil.Process(os.getpid())
        sys_stats = {
            "rss_mb": round(proc.memory_info().rss / 1_048_576, 1),
            "cpu_percent": proc.cpu_percent(interval=0.1),
            "open_files": len(proc.open_files()),
            "threads": proc.num_threads(),
            "system_cpu_percent": psutil.cpu_percent(interval=0.1),
            "system_mem_percent": psutil.virtual_memory().percent,
        }
    except ImportError:
        sys_stats = {"available": False}
    except Exception as exc:
        sys_stats = {"error": str(exc)}

    return {
        "status": "ok",
        "version": cfg.app_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime": f"{uptime_h}h {uptime_m}m",
        "uptime_seconds": uptime_seconds,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "database": db_stats,
        "system": sys_stats,
        "ai": {
            "primary": cfg.primary_ai,
            "anthropic_configured": bool(cfg.anthropic_api_key),
            "groq_configured": bool(cfg.groq_api_key),
            "gemini_configured": bool(cfg.gemini_api_key),
        },
    }


@router.get("/mi-dia")
def mi_dia(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Dashboard personal del gestor: un solo request para arrancar el día.

    Retorna:
      - tareas: pendientes de hoy + totales del checklist diario
      - glosas: asignadas al gestor, vencen próximas 48h, recientes sin dictamen
      - alertas: número de glosas próximas a vencer
      - saludo: mensaje motivacional con el nombre del gestor
    """
    from datetime import date, timedelta

    from sqlalchemy import func

    hoy = date.today().isoformat()

    # Tareas del gestor para hoy
    tareas_hoy = (
        db.query(TareaDiariaRecord)
        .filter(
            TareaDiariaRecord.usuario_email == current_user.email,
            TareaDiariaRecord.fecha_para == hoy,
        )
        .all()
    )
    tareas_pendientes = sum(1 for t in tareas_hoy if not t.completada)
    tareas_completadas = sum(1 for t in tareas_hoy if t.completada)

    # Glosas del gestor
    email = current_user.email
    glosas_asignadas = (
        db.query(func.count(GlosaRecord.id))
        .filter(
            GlosaRecord.auditor_email == email,
            GlosaRecord.estado.notin_(["CERRADA", "PAPELERA", "ACEPTADA"]),
        )
        .scalar()
        or 0
    )
    glosas_vencen_48h = (
        db.query(func.count(GlosaRecord.id))
        .filter(
            GlosaRecord.auditor_email == email,
            GlosaRecord.fecha_vencimiento.isnot(None),
            GlosaRecord.fecha_vencimiento.between(
                datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc),
                datetime.combine(date.today() + timedelta(days=2), datetime.min.time()).replace(
                    tzinfo=timezone.utc
                ),
            ),
            GlosaRecord.estado.notin_(["CERRADA", "PAPELERA"]),
        )
        .scalar()
        or 0
    )
    glosas_sin_dictamen = (
        db.query(func.count(GlosaRecord.id))
        .filter(
            GlosaRecord.auditor_email == email,
            GlosaRecord.dictamen.is_(None),
            GlosaRecord.estado.notin_(["CERRADA", "PAPELERA"]),
        )
        .scalar()
        or 0
    )

    # Saludo según la hora
    hora = datetime.now(timezone.utc).hour
    if hora < 12:
        saludo_base = "Buenos días"
    elif hora < 18:
        saludo_base = "Buenas tardes"
    else:
        saludo_base = "Buenas noches"
    nombre = (current_user.nombre or "").split()[0] if current_user.nombre else "gestor"
    saludo = f"{saludo_base}, {nombre}."
    if tareas_pendientes > 0:
        saludo += f" Tienes {tareas_pendientes} tarea(s) pendiente(s) hoy."
    if glosas_vencen_48h > 0:
        saludo += f" ⚠ {glosas_vencen_48h} glosa(s) vencen en las próximas 48h."

    return {
        "fecha": hoy,
        "saludo": saludo,
        "tareas": {
            "pendientes": tareas_pendientes,
            "completadas": tareas_completadas,
            "total": len(tareas_hoy),
        },
        "glosas": {
            "asignadas_activas": glosas_asignadas,
            "vencen_48h": glosas_vencen_48h,
            "sin_dictamen": glosas_sin_dictamen,
        },
        "alertas": {
            "nivel": "ALTA"
            if glosas_vencen_48h > 5
            else ("MEDIA" if glosas_vencen_48h > 0 else "OK"),
            "vencen_48h": glosas_vencen_48h,
        },
    }


@router.get("/sistema/diagnostico-ia")
def diagnostico_ia(
    horas: int = 24,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Diagnóstico de salud de los proveedores IA en las últimas N horas.

    Útil cuando producción muestra dictámenes vacíos / lentos. Permite
    saber qué proveedor está degradado SIN abrir Fly logs.

    Params:
      horas (default 24): ventana de análisis (1..168)

    Retorna por proveedor:
      - total_calls
      - latency p50 / p95 / p99 (ms)
      - tasa de éxito aproximada (calls con output_tokens > 0)
      - cache hit rate
      - tokens totales (input/output)
      - costo USD acumulado
      - último modelo usado

    Estado global: OK | DEGRADADO (si algún proveedor con >=10 calls
    tiene tasa_exito < 80% o p95 > 30s).
    """
    from datetime import timedelta

    from app.models.db import AICallRecord

    try:
        horas_int = int(horas)
    except (TypeError, ValueError):
        horas_int = 24
    horas = max(1, min(horas_int, 168))
    desde = datetime.now(timezone.utc) - timedelta(hours=horas)

    calls = (
        db.query(AICallRecord)
        .filter(AICallRecord.creado_en >= desde)
        .order_by(AICallRecord.creado_en.desc())
        .limit(5000)
        .all()
    )

    if not calls:
        return {
            "ventana_horas": horas,
            "total_calls": 0,
            "estado": "SIN_DATOS",
            "proveedores": {},
            "mensaje": "Sin llamadas IA en la ventana solicitada.",
        }

    por_prov: dict[str, list] = {}
    for c in calls:
        por_prov.setdefault(c.proveedor or "desconocido", []).append(c)

    def _percentil(valores: list[int], p: float) -> int:
        if not valores:
            return 0
        ordenados = sorted(valores)
        idx = min(len(ordenados) - 1, int(len(ordenados) * p))
        return int(ordenados[idx])

    proveedores: dict = {}
    for prov, items in por_prov.items():
        latencias = [int(c.latency_ms or 0) for c in items]
        con_output = sum(1 for c in items if (c.output_tokens or 0) > 0)
        cache_hits = sum(1 for c in items if (c.cache_read_input_tokens or 0) > 0)
        ultimo_modelo = items[0].modelo if items else ""
        proveedores[prov] = {
            "total_calls": len(items),
            "latency_ms": {
                "p50": _percentil(latencias, 0.50),
                "p95": _percentil(latencias, 0.95),
                "p99": _percentil(latencias, 0.99),
            },
            "tasa_exito_pct": round(100.0 * con_output / len(items), 1),
            "cache_hit_rate_pct": round(100.0 * cache_hits / len(items), 1),
            "tokens_input": sum(c.input_tokens or 0 for c in items),
            "tokens_output": sum(c.output_tokens or 0 for c in items),
            "costo_usd": round(sum(c.cost_usd or 0.0 for c in items), 4),
            "ultimo_modelo": ultimo_modelo,
        }

    estado = "OK"
    razones = []
    for prov, st in proveedores.items():
        if st["total_calls"] >= 10:
            if st["tasa_exito_pct"] < 80:
                estado = "DEGRADADO"
                razones.append(f"{prov} tasa_exito={st['tasa_exito_pct']}%")
            if st["latency_ms"]["p95"] > 30000:
                estado = "DEGRADADO"
                razones.append(f"{prov} p95={st['latency_ms']['p95']}ms")

    return {
        "ventana_horas": horas,
        "total_calls": len(calls),
        "estado": estado,
        "razones_degradacion": razones,
        "proveedores": proveedores,
    }


@router.get("/debug/sentry-test", include_in_schema=False)
def sentry_test(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Endpoint para verificar que Sentry captura errores.

    Solo accesible por SUPER_ADMIN. Lanza una excepción intencional —
    debería aparecer en el dashboard de Sentry a los pocos segundos.
    """
    if current_user.rol != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Solo SUPER_ADMIN puede correr este test")
    raise RuntimeError(
        f"[SENTRY_TEST] Test de integración disparado por {current_user.email} "
        f"en {datetime.now().isoformat()}. Si ves este mensaje en Sentry, funciona correctamente."
    )
