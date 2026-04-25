"""Endpoints de health-check y diagnóstico (R51 P6).

Extraídos de app/main.py. Agrupa:
  - GET /health            → healthcheck público (status + version + banner)
  - GET /debug/sentry-test → test intencional de integración Sentry
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.models.db import UsuarioRecord

router = APIRouter(tags=["sistema"])

cfg = get_settings()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": cfg.app_version,
        "banner": (cfg.banner_capacitacion or "").strip(),
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
