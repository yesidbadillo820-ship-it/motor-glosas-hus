"""Adjuntos (screenshots, documentos) en conciliaciones."""
import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db import AdjuntoConciliacionRecord, ConciliacionRecord, UsuarioRecord
from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/conciliaciones/{conciliacion_id}/adjuntos", tags=["adjuntos"])

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB por archivo
_TIPOS_OK = {"image/png", "image/jpeg", "image/jpg", "image/gif", "application/pdf"}


@router.get("/")
def listar(
    conciliacion_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    rows = db.query(AdjuntoConciliacionRecord).filter(
        AdjuntoConciliacionRecord.conciliacion_id == conciliacion_id
    ).all()
    return [
        {
            "id": r.id,
            "nombre": r.nombre,
            "mime_type": r.mime_type,
            "tamano_bytes": r.tamano_bytes,
            "subido_por": r.subido_por,
            "subido_en": r.subido_en.isoformat() if r.subido_en else None,
        }
        for r in rows
    ]


@router.post("/", status_code=201)
async def subir(
    conciliacion_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Sube un screenshot/PDF como evidencia de la conciliación."""
    if not db.query(ConciliacionRecord).filter(ConciliacionRecord.id == conciliacion_id).first():
        raise HTTPException(404, "Conciliación no encontrada")
    contenido = await archivo.read()
    if len(contenido) > _MAX_BYTES:
        raise HTTPException(400, f"Archivo excede 10 MB ({len(contenido)} bytes)")
    mime = archivo.content_type or ""
    if mime not in _TIPOS_OK:
        raise HTTPException(400, f"Tipo no permitido: {mime}. Usa PNG/JPG/PDF.")

    reg = AdjuntoConciliacionRecord(
        conciliacion_id=conciliacion_id,
        nombre=archivo.filename or "archivo",
        mime_type=mime,
        tamano_bytes=len(contenido),
        contenido_b64=base64.b64encode(contenido).decode("ascii"),
        subido_por=current_user.email,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="ADJUNTO_CONCILIACION", tabla="conciliaciones",
        registro_id=conciliacion_id,
        detalle=f"Subido: {archivo.filename} ({len(contenido)} bytes)",
    )
    return {"id": reg.id, "message": "Adjunto subido"}


@router.get("/{adjunto_id}/descargar")
def descargar(
    conciliacion_id: int,
    adjunto_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r = db.query(AdjuntoConciliacionRecord).filter(
        AdjuntoConciliacionRecord.id == adjunto_id,
        AdjuntoConciliacionRecord.conciliacion_id == conciliacion_id,
    ).first()
    if not r:
        raise HTTPException(404, "Adjunto no encontrado")
    try:
        data = base64.b64decode(r.contenido_b64)
    except Exception:
        raise HTTPException(500, "Adjunto corrupto")
    return Response(
        content=data,
        media_type=r.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{r.nombre}"'},
    )


@router.delete("/{adjunto_id}")
def eliminar(
    conciliacion_id: int,
    adjunto_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    r = db.query(AdjuntoConciliacionRecord).filter(
        AdjuntoConciliacionRecord.id == adjunto_id,
        AdjuntoConciliacionRecord.conciliacion_id == conciliacion_id,
    ).first()
    if not r:
        raise HTTPException(404, "Adjunto no encontrado")
    db.delete(r)
    db.commit()
    return {"message": "Adjunto eliminado"}
