"""Endpoints de health-check y diagnóstico (R51 P6).

Extraídos de app/main.py. Agrupa:
  - GET /health            → healthcheck público (status + version + banner)
  - GET /health/detail     → métricas detalladas del sistema (requiere auth)
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
from app.database import SessionLocal
from app.models.db import GlosaRecord, UsuarioRecord

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
