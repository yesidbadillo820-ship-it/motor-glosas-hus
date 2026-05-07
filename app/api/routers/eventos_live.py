"""Eventos en vivo (B.2): polling-based "real-time" para que la UI
actualice paneles sin que el usuario tenga que recargar.

Estrategia: el frontend llama GET /eventos/recientes?since=<ISO> cada
8-12 segundos. El backend devuelve los eventos del audit_log con
accion en una whitelist de tipos relevantes (CREAR, ASIGNAR,
DECISION_EPS, etc.) desde ese timestamp.

No requiere WebSocket ni infraestructura adicional, funciona detras
de proxies/firewalls y es compatible con multi-instancia. Costo BD
es minimo: 1 query indexada con filtro de timestamp.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import AuditLogRecord, UsuarioRecord


router = APIRouter(prefix="/eventos", tags=["eventos-live"])


# Acciones del audit_log que la UI quiere reflejar en vivo.
# Se mantiene corta para no saturar el feed de eventos triviales.
ACCIONES_LIVE = {
    "CREAR",                # nueva glosa o conciliacion
    "ASIGNAR",              # glosa asignada a otro auditor
    "BULK_ASIGNAR",         # asignacion en bulk
    "DECISION_EPS",         # EPS LEVANTO/RATIFICO
    "DECISION_EPS_LOTE",    # decision en bulk
    "BULK_UPDATE_ESTADO",   # cambio masivo de estado
    "WORKFLOW",             # transicion respondida/conciliada/etc
    "IMPORTAR_RECEPCION",   # importacion masiva
    "GENERAR_LOTE",         # nuevo lote IA
    "REANALIZAR_GLOSA",     # re-analisis individual
    "CLONAR_GLOSA",         # clonacion
}


@router.get("/recientes")
def eventos_recientes(
    since: Optional[str] = Query(None, description="ISO timestamp UTC"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve eventos relevantes desde un timestamp dado.

    Si no se pasa `since`, usa los ultimos 60 segundos como ventana.
    El cliente debe persistir el `timestamp` del ultimo evento
    recibido para usarlo como `since` en la siguiente llamada
    (cursor-style polling).
    """
    if since:
        try:
            cursor = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if cursor.tzinfo is None:
                cursor = cursor.replace(tzinfo=timezone.utc)
        except Exception:
            cursor = ahora_utc() - timedelta(seconds=60)
    else:
        cursor = ahora_utc() - timedelta(seconds=60)

    rows = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp > cursor)
        .filter(AuditLogRecord.accion.in_(ACCIONES_LIVE))
        .order_by(AuditLogRecord.timestamp.asc())
        .limit(limit)
        .all()
    )

    eventos = []
    for r in rows:
        eventos.append({
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "accion": r.accion,
            "tabla": r.tabla,
            "registro_id": r.registro_id,
            "usuario": (r.usuario_email or "").split("@")[0] if r.usuario_email else None,
            "rol": r.usuario_rol,
            "campo": r.campo,
            "valor_anterior": r.valor_anterior,
            "valor_nuevo": r.valor_nuevo,
            "detalle": r.detalle,
        })

    server_now = ahora_utc().isoformat()
    return {
        "server_time": server_now,
        "since": cursor.isoformat(),
        "count": len(eventos),
        "eventos": eventos,
    }


@router.get("/heartbeat")
def heartbeat(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Heartbeat ligero — solo devuelve hora del servidor.

    Util para que el cliente sincronice su `since` cursor con la hora
    del servidor (evita drift por reloj local).
    """
    return {"server_time": ahora_utc().isoformat()}
