"""Lotes de portal: subida del Excel consolidado + cola del agente local.

Dos routers: `router` (usuarios de la app — subir lote, ver semáforo) y
`agente_router` (el agente local del PC del hospital — reclamar tarea,
descargar el Excel, reportar resultados). El agente se autentica con el
token estático AGENTE_LOTES_TOKEN, no con JWT de usuario.
"""

from __future__ import annotations

import json
import re
import secrets

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Response, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, defer

from app.api.deps import get_auditor_o_superior, get_usuario_actual
from app.core.config import get_settings
from app.database import get_db
from app.models.db import (
    TAREA_ESTADO_RECLAMADA,
    FacturaLoteRecord,
    LoteRecord,
    TareaLoteRecord,
    UsuarioRecord,
)
from app.services import lotes_service

router = APIRouter(prefix="/lotes", tags=["lotes"])
agente_router = APIRouter(prefix="/agente/lotes", tags=["agente-lotes"])


# ─── Endpoints de usuario ────────────────────────────────────────────────────


def _lote_a_dict(lote: LoteRecord) -> dict:
    return {
        "id": lote.id,
        "creado_en": lote.creado_en.isoformat() if lote.creado_en else None,
        "creado_por": lote.creado_por,
        "pagador": lote.pagador,
        "nombre_archivo": lote.nombre_archivo,
        "hoja": lote.hoja,
        "incluir_calidad": bool(lote.incluir_calidad),
        "estado": lote.estado,
        "total_facturas": lote.total_facturas,
        "total_glosas": lote.total_glosas,
        "total_calidad": lote.total_calidad,
        "resumen": json.loads(lote.resumen) if lote.resumen else None,
        "actualizado_en": lote.actualizado_en.isoformat() if lote.actualizado_en else None,
    }


@router.get("/pagadores")
def pagadores_encolables(
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Qué pagadores se pueden encolar hoy, y qué archivo pide cada uno.

    Sale del registro de perfiles (`services/perfiles_lote`), el mismo que usa
    el agente para saber qué bot correr. Antes esto era el conjunto literal
    `{"COOSALUD"}` escrito en el servicio: habilitar un pagador exigía tocar
    tres archivos y desplegar, aunque su bot ya existiera en `tools/`.
    """
    from app.services import perfiles_lote

    return {"total": len(perfiles_lote.PERFILES), "pagadores": perfiles_lote.catalogo()}


@router.post("/", status_code=201)
async def crear_lote(
    archivo: UploadFile = File(...),
    pagador: str = Form("COOSALUD"),
    hoja: str = Form("BASE"),
    incluir_calidad: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Sube el Excel consolidado y encola la corrida del bot."""
    # Ronda 31: sanear el nombre — el agente local lo usa para escribir el
    # archivo en disco (path traversal en el PC del HUS) y el motor lo
    # refleja en Content-Disposition. El servidor es Linux, así que
    # Path(...).name NO recorta el '\' de Windows: se recortan AMBOS
    # separadores y se rechazan control chars/comillas.
    raw = archivo.filename or "lote.xlsx"
    nombre = re.split(r"[\\/]", raw)[-1].strip() or "lote.xlsx"
    if nombre in (".", "..") or any(c in nombre for c in '"\r\n\x00'):
        raise HTTPException(400, "Nombre de archivo inválido.")
    if not nombre.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "El archivo debe ser un Excel (.xlsx / .xlsm).")
    if archivo.size is not None and archivo.size > lotes_service.MAX_EXCEL_BYTES:
        raise HTTPException(
            400, f"Archivo excede {lotes_service.MAX_EXCEL_BYTES // (1024 * 1024)} MB."
        )
    contenido = await archivo.read()
    if len(contenido) > lotes_service.MAX_EXCEL_BYTES:
        raise HTTPException(
            400, f"Archivo excede {lotes_service.MAX_EXCEL_BYTES // (1024 * 1024)} MB."
        )
    try:
        lote = lotes_service.crear_lote(
            db,
            contenido=contenido,
            nombre_archivo=nombre,
            pagador=pagador,
            hoja=hoja,
            incluir_calidad=incluir_calidad,
            creado_por=current_user.email,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _lote_a_dict(lote)


@router.get("/")
def listar_lotes(
    limite: int = 50,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    # Ronda 31: defer(excel_archivo) — el listado NO usa el BLOB (ver
    # _lote_a_dict), pero sin esto traía hasta 200 archivos de 20MB a RAM
    # y reventaba la e2-micro de 1GB. descargar_excel sigue trayéndolo con
    # su carga normal (una sola fila).
    lotes = (
        db.query(LoteRecord)
        .options(defer(LoteRecord.excel_archivo))
        .order_by(LoteRecord.id.desc())
        .limit(max(1, min(limite, 200)))
        .all()
    )
    return [_lote_a_dict(lo) for lo in lotes]


@router.get("/{lote_id}")
def detalle_lote(
    lote_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    lote = db.query(LoteRecord).filter(LoteRecord.id == lote_id).first()
    if not lote:
        raise HTTPException(404, "Lote no encontrado")
    facturas = (
        db.query(FacturaLoteRecord)
        .filter(FacturaLoteRecord.lote_id == lote_id)
        .order_by(FacturaLoteRecord.factura)
        .all()
    )
    tareas = (
        db.query(TareaLoteRecord)
        .filter(TareaLoteRecord.lote_id == lote_id)
        .order_by(TareaLoteRecord.id)
        .all()
    )
    out = _lote_a_dict(lote)
    out["facturas"] = [
        {
            "factura": f.factura,
            "grupos": f.grupos,
            "glosas": f.glosas,
            "calidad": f.calidad,
            "requiere_soporte": bool(f.requiere_soporte),
            "estado": f.estado,
            "detalle": f.detalle,
            "actualizado_en": f.actualizado_en.isoformat() if f.actualizado_en else None,
        }
        for f in facturas
    ]
    out["tareas"] = [
        {
            "id": t.id,
            "tipo": t.tipo,
            "estado": t.estado,
            "agente": t.agente,
            "reclamada_en": t.reclamada_en.isoformat() if t.reclamada_en else None,
            "terminada_en": t.terminada_en.isoformat() if t.terminada_en else None,
            "error": t.error,
        }
        for t in tareas
    ]
    return out


# ─── Endpoints del agente local ──────────────────────────────────────────────


def verificar_token_agente(x_agente_token: str = Header(default="")) -> None:
    token = get_settings().agente_lotes_token
    if not token:
        raise HTTPException(503, "Agente de lotes deshabilitado (falta AGENTE_LOTES_TOKEN).")
    if not secrets.compare_digest(x_agente_token, token):
        raise HTTPException(401, "Token de agente inválido.")


class ReclamarBody(BaseModel):
    agente: str = Field(min_length=1, max_length=200)


class ResultadoFactura(BaseModel):
    factura: str
    estado: str
    detalle: str = ""


class CompletarBody(BaseModel):
    exito: bool
    resultados: list[ResultadoFactura] = []
    error: str | None = None


@agente_router.post("/tareas/reclamar")
def reclamar_tarea(
    body: ReclamarBody,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    tarea = lotes_service.reclamar_tarea(db, body.agente)
    if tarea is None:
        return Response(status_code=204)
    lote = db.query(LoteRecord).filter(LoteRecord.id == tarea.lote_id).first()
    return {
        "tarea_id": tarea.id,
        "tipo": tarea.tipo,
        "lote_id": lote.id,
        "pagador": lote.pagador,
        "nombre_archivo": lote.nombre_archivo,
        "hoja": lote.hoja,
        "incluir_calidad": bool(lote.incluir_calidad),
        "total_facturas": lote.total_facturas,
    }


def _tarea_reclamada_o_404(db: Session, tarea_id: int) -> TareaLoteRecord:
    tarea = db.query(TareaLoteRecord).filter(TareaLoteRecord.id == tarea_id).first()
    if not tarea:
        raise HTTPException(404, "Tarea no encontrada")
    if tarea.estado != TAREA_ESTADO_RECLAMADA:
        raise HTTPException(409, f"La tarea está en estado {tarea.estado}, no RECLAMADA.")
    return tarea


@agente_router.get("/tareas/{tarea_id}/excel")
def descargar_excel(
    tarea_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    tarea = _tarea_reclamada_o_404(db, tarea_id)
    lote = db.query(LoteRecord).filter(LoteRecord.id == tarea.lote_id).first()
    # Ronda 31: defensa en profundidad para lotes viejos creados antes del
    # saneo en crear_lote — un nombre con comillas/CRLF rompería el header.
    _nombre = re.sub(r'[\r\n"\\]', "_", lote.nombre_archivo or "lote.xlsx")[:300] or "lote.xlsx"
    return Response(
        content=lote.excel_archivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_nombre}"'},
    )


@agente_router.post("/tareas/{tarea_id}/progreso")
def reportar_progreso(
    tarea_id: int,
    body: CompletarBody,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    """Actualización incremental mientras el bot corre (el CSV es append-as-you-go)."""
    tarea = _tarea_reclamada_o_404(db, tarea_id)
    aplicadas = lotes_service.aplicar_resultados(
        db, tarea.lote_id, [r.model_dump() for r in body.resultados]
    )
    db.commit()
    return {"aplicadas": aplicadas}


@agente_router.post("/tareas/{tarea_id}/completar")
def completar_tarea(
    tarea_id: int,
    body: CompletarBody,
    db: Session = Depends(get_db),
    _: None = Depends(verificar_token_agente),
):
    tarea = _tarea_reclamada_o_404(db, tarea_id)
    lote = lotes_service.completar_tarea(
        db,
        tarea,
        exito=body.exito,
        resultados=[r.model_dump() for r in body.resultados],
        error=body.error,
    )
    return _lote_a_dict(lote)
