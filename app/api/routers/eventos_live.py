"""Server-Sent Events (SSE) para importación masiva y notificaciones en tiempo real.

Endpoints:
  GET /eventos/importar/{rec_id}  — progreso de una importación en curso
  GET /eventos/ping               — keepalive / verificar SSE funciona
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import AuditLogRecord, UsuarioRecord

router = APIRouter(prefix="/eventos", tags=["eventos"])

# Cola de eventos de importación por rec_id.
# Clave: rec_id (str), Valor: asyncio.Queue con mensajes {"tipo": ..., "datos": ...}
_COLAS_IMPORTACION: dict[str, asyncio.Queue] = {}
_MAX_COLA = 100


def publicar_evento_importacion(rec_id: str, tipo: str, datos: dict) -> None:
    """Publica un evento en la cola del rec_id dado.

    Llamar desde el servicio de importación para notificar progreso.
    Si no hay suscriptores, el evento se descarta silenciosamente.
    """
    cola = _COLAS_IMPORTACION.get(str(rec_id))
    if cola and not cola.full():
        try:
            cola.put_nowait({"tipo": tipo, "datos": datos})
        except asyncio.QueueFull:
            pass


async def _generar_sse(
    cola: asyncio.Queue,
    timeout_s: float = 120.0,
) -> AsyncGenerator[str, None]:
    """Genera el stream SSE desde una cola hasta que se llena el timeout."""
    elapsed = 0.0
    tick = 0.5
    while elapsed < timeout_s:
        try:
            msg = cola.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(tick)
            elapsed += tick
            if int(elapsed) % 15 == 0:
                # Keepalive comment cada 15s para evitar que proxies corten la conexión
                yield ": keepalive\n\n"
            continue

        # Evento SSE estándar
        payload = json.dumps(msg["datos"], ensure_ascii=False)
        yield f"event: {msg['tipo']}\ndata: {payload}\n\n"

        if msg["tipo"] in ("finalizado", "error"):
            break

    yield "event: timeout\ndata: {}\n\n"


@router.get("/importar/{rec_id}")
async def sse_importar(
    rec_id: str,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> StreamingResponse:
    """Stream SSE de progreso de importación.

    El cliente debe escuchar:
      - evento `progreso`: {"fila": N, "total": M, "msg": "..."}
      - evento `finalizado`: {"total": N, "errores": K}
      - evento `error`: {"msg": "..."}
      - evento `timeout`: cierre limpio si el cliente no se reconecta

    Ejemplo JS:
      const es = new EventSource('/eventos/importar/42', {headers: {Authorization: 'Bearer ...'}});
      es.addEventListener('progreso', e => console.log(JSON.parse(e.data)));
    """
    cola: asyncio.Queue = asyncio.Queue(maxsize=_MAX_COLA)
    _COLAS_IMPORTACION[str(rec_id)] = cola

    async def cleanup() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _generar_sse(cola):
                yield chunk
        finally:
            # Ronda 30: solo borrar la cola si sigue siendo LA NUESTRA. Si un
            # segundo suscriptor del mismo rec_id la reemplazó, al desconectar
            # el primero borraba la cola del segundo (patrón ya usado en
            # sse_analizar). El finally garantiza limpieza aun si el cliente
            # corta la conexión.
            if _COLAS_IMPORTACION.get(str(rec_id)) is cola:
                _COLAS_IMPORTACION.pop(str(rec_id), None)

    return StreamingResponse(
        cleanup(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/analizar/{trace_id}")
async def sse_analizar(
    trace_id: str,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> StreamingResponse:
    """Stream SSE de progreso en vivo del análisis de UNA glosa.

    Protocolo:
      1. Frontend genera uuid (trace_id) y abre EventSource a /eventos/analizar/{trace_id}
      2. Frontend hace POST /analizar con form field 'trace_id'
      3. El endpoint analizar publica eventos en cada etapa via
         app.services.progreso_analisis.publicar(trace_id, etapa, datos)
      4. Esta cola los serializa como SSE 'event: etapa\\ndata: {...}\\n\\n'

    Eventos emitidos por el endpoint /analizar (orden típico):
      - inicio          {fecha, eps, codigo_glosa}
      - pdfs_extraidos  {n_archivos, n_caracteres}
      - tarifa_lookup   {encontrada: bool, valor_pactado?}
      - few_shots       {n_plantillas}
      - ia_iniciada     {proveedor, modelo}
      - ia_completada   {latencia_ms, tokens_output}
      - persistido      {glosa_id, estado, score}
      - finalizado      {ok: true}

    Eventos auto-emitidos por el stream:
      - keepalive      cada 15s (comentario SSE para no cortar la conexión)
      - timeout        si pasan 60s sin ningún evento del análisis
    """
    from app.services.progreso_analisis import (
        cerrar_cola,
        obtener_cola,
    )

    cola = obtener_cola(trace_id)

    async def _stream() -> AsyncGenerator[str, None]:
        elapsed = 0.0
        tick = 0.5
        timeout_s = 60.0
        try:
            while elapsed < timeout_s:
                try:
                    msg = cola.get_nowait()
                except asyncio.QueueEmpty:
                    await asyncio.sleep(tick)
                    elapsed += tick
                    if int(elapsed) % 15 == 0:
                        yield ": keepalive\n\n"
                    continue
                payload = json.dumps(msg["datos"], ensure_ascii=False)
                yield f"event: {msg['etapa']}\ndata: {payload}\n\n"
                if msg["etapa"] in ("finalizado", "error"):
                    return
                # Resetear timeout: hubo actividad
                elapsed = 0.0
            yield "event: timeout\ndata: {}\n\n"
        finally:
            cerrar_cola(trace_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/ping")
async def sse_ping(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> StreamingResponse:
    """Endpoint de prueba SSE: envía 3 pings y cierra."""

    async def _gen() -> AsyncGenerator[str, None]:
        for i in range(3):
            yield f'event: ping\ndata: {{"seq": {i + 1}}}\n\n'
            await asyncio.sleep(0.1)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


# ─── Polling de eventos (repuesto 13-08-2026) ───────────────────────────────
# Estas dos rutas se borraron el 09-05-2026 (commit c4023e8, "cleanup:
# eventos_live") y después se creó OTRO eventos_live.py, con el mismo prefijo
# pero con SSE. La pantalla siguió llamando a las de polling: desde ese día,
# los paneles del portal dejaron de refrescarse solos y nadie se enteró,
# porque el JavaScript se traga el error en silencio.
#
# Conviven con las de SSE: son mecanismos distintos para cosas distintas. El
# polling refresca los paneles cada 8-12 segundos y funciona detrás de
# proxies y firewalls; el SSE sirve para seguir una importación en curso.
# Acciones del audit_log que la UI quiere reflejar en vivo.
# Se mantiene corta para no saturar el feed de eventos triviales.
ACCIONES_LIVE = {
    "CREAR",  # nueva glosa o conciliacion
    "ASIGNAR",  # glosa asignada a otro auditor
    "BULK_ASIGNAR",  # asignacion en bulk
    "DECISION_EPS",  # EPS LEVANTO/RATIFICO
    "DECISION_EPS_LOTE",  # decision en bulk
    "BULK_UPDATE_ESTADO",  # cambio masivo de estado
    "WORKFLOW",  # transicion respondida/conciliada/etc
    "IMPORTAR_RECEPCION",  # importacion masiva
    "GENERAR_LOTE",  # nuevo lote IA
    "REANALIZAR_GLOSA",  # re-analisis individual
    "CLONAR_GLOSA",  # clonacion
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
        eventos.append(
            {
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
            }
        )

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
