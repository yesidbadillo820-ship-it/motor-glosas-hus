"""Endpoints para auto-descubrimiento de soportes en el share de radicación.

Flujo:
  GET  /soportes-auto/healthz                  → estado público para monitor
  GET  /soportes-auto/stats                    → estado detallado (auth)
  GET  /soportes-auto/factura/{numero}         → soportes detectados (auth + audit PHI)
  POST /soportes-auto/reindex                  → rebuild manual (auditor+)

Cada `GET /factura/{numero}` registra acceso PHI en audit_log con
acción `LISTAR_SOPORTES_FACTURA` — obligatorio para auditoría de
historias clínicas.
"""
from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.database import get_db
from app.models.db import UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.services.soportes_autodiscovery_service import get_indexer

router = APIRouter(prefix="/soportes-auto", tags=["soportes-auto"])

# Si el último build fue hace más de este umbral, el healthz reporta degradado.
_UMBRAL_BUILD_OBSOLETO_SEG = 25 * 3600  # 25 horas (1 ciclo + margen)


@router.get("/healthz")
def healthz():
    """Health check público — no requiere auth, para monitor externo.

    Retorna:
      200 + {status: "ok", ...}        → indexador caliente y raíz accesible
      503 + {status: "degraded", ...}  → mount caído, build obsoleto o error
    """
    s = get_indexer().stats()
    razones = []
    if not s["raiz_existe"]:
        razones.append(f"raiz_no_accesible:{s['raiz']}")
    if s["ultimo_error"]:
        razones.append(f"error:{s['ultimo_error']}")
    if s["construido_en_epoch"] == 0:
        razones.append("indice_nunca_construido")
    elif s["construido_hace_seg"] is not None and s["construido_hace_seg"] > _UMBRAL_BUILD_OBSOLETO_SEG:
        razones.append(f"build_obsoleto:{s['construido_hace_seg']/3600:.1f}h")

    body = {
        "status": "ok" if not razones else "degraded",
        "facturas_indexadas": s["facturas_indexadas"],
        "archivos_indexados": s["archivos_indexados"],
        "construido_hace_seg": s["construido_hace_seg"],
        "raiz": s["raiz"],
        "razones_degradacion": razones,
    }
    if razones:
        # 503 hace que el balanceador / monitor lo detecte como caído
        raise HTTPException(status_code=503, detail=body)
    return body


@router.get("/stats")
def stats(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Estado detallado del indexador. Requiere auth."""
    return get_indexer().stats()


@router.get("/factura/{numero}")
def soportes_de_factura(
    numero: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve los soportes detectados en disco para una factura.

    Acepta el número en cualquier formato (`HUS487523`, `HUS0000495050`,
    `495050`) — internamente se normaliza por la parte numérica.

    Auditoría PHI: cada llamada registra `LISTAR_SOPORTES_FACTURA` con
    factura, cantidad de archivos y usuario. Es obligatorio porque
    saber qué historias clínicas existen para un paciente ya es PHI.
    """
    if not numero or len(numero) < 3:
        raise HTTPException(400, "Número de factura inválido")
    indexer = get_indexer()
    soportes = indexer.lookup(numero)

    # Auditoría PHI
    try:
        ip = request.client.host if request.client else None
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="LISTAR_SOPORTES_FACTURA",
            tabla="soportes_share",
            detalle=(
                f"factura={numero[:50]} encontrados={len(soportes)} "
                f"tipos={sorted({s['tipo_codigo'] for s in soportes})}"
            ),
            ip=ip,
        )
    except Exception:
        pass  # nunca tumbar la respuesta por fallo de audit

    return {
        "factura": numero,
        "soportes": soportes,
        "total": len(soportes),
        "tipos_detectados": sorted({s["tipo_codigo"] for s in soportes}),
    }


@router.post("/reindex")
def reindex(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Fuerza una reconstrucción del índice. Auditor+ por costo de I/O."""
    inicio = time.time()
    stats_resultado = get_indexer().rebuild()
    duracion = round(time.time() - inicio, 2)
    try:
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=getattr(current_user, "rol", "") or "",
            accion="REINDEX_SOPORTES",
            tabla="soportes_share",
            detalle=(
                f"archivos={stats_resultado['archivos_indexados']} "
                f"facturas={stats_resultado['facturas_indexadas']} "
                f"duracion_s={duracion} "
                f"error={stats_resultado.get('ultimo_error') or 'ninguno'}"
            ),
            ip=request.client.host if request.client else None,
        )
    except Exception:
        pass
    return {"duracion_segundos": duracion, **stats_resultado}
