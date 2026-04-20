"""Historial de versiones del dictamen + restauración.

Cada vez que se genera, refina o regenera un dictamen, se guarda snapshot.
El auditor puede revisar cómo cambió y restaurar una versión anterior.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.db import DictamenVersionRecord, GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/glosas/{glosa_id}/versiones", tags=["versiones"])


@router.get("/")
def listar(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if not db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first():
        raise HTTPException(404, "Glosa no encontrada")
    q = (
        db.query(DictamenVersionRecord)
        .filter(DictamenVersionRecord.glosa_id == glosa_id)
        .order_by(DictamenVersionRecord.creado_en.desc())
    )
    return [
        {
            "id": v.id,
            "accion": v.accion,
            "mensaje_refinar": v.mensaje_refinar,
            "autor_email": v.autor_email,
            "creado_en": v.creado_en.isoformat() if v.creado_en else None,
            "preview": (v.dictamen_html or "")[:300],
        }
        for v in q.limit(100).all()
    ]


@router.get("/{version_id}")
def obtener(
    glosa_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    v = db.query(DictamenVersionRecord).filter(
        DictamenVersionRecord.id == version_id,
        DictamenVersionRecord.glosa_id == glosa_id,
    ).first()
    if not v:
        raise HTTPException(404, "Versión no encontrada")
    return {
        "id": v.id,
        "glosa_id": v.glosa_id,
        "accion": v.accion,
        "mensaje_refinar": v.mensaje_refinar,
        "autor_email": v.autor_email,
        "creado_en": v.creado_en.isoformat() if v.creado_en else None,
        "dictamen_html": v.dictamen_html,
    }


@router.post("/{version_id}/restaurar")
def restaurar(
    glosa_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Restaura una versión anterior del dictamen como la versión vigente."""
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    v = db.query(DictamenVersionRecord).filter(
        DictamenVersionRecord.id == version_id,
        DictamenVersionRecord.glosa_id == glosa_id,
    ).first()
    if not v:
        raise HTTPException(404, "Versión no encontrada")

    # Snapshot del dictamen actual antes de sobrescribir
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html=glosa.dictamen or "",
        accion="SNAPSHOT_PRE_RESTAURAR",
        autor_email=current_user.email,
    ))
    glosa.dictamen = v.dictamen_html
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html=v.dictamen_html,
        accion="RESTAURAR",
        mensaje_refinar=f"Restaurada desde versión #{version_id}",
        autor_email=current_user.email,
    ))
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="RESTAURAR_DICTAMEN", tabla="historial",
        registro_id=glosa_id,
        detalle=f"Restauró versión #{version_id}",
    )
    return {"message": "Dictamen restaurado", "version_restaurada": version_id}


def guardar_version(
    db: Session,
    glosa_id: int,
    dictamen_html: str,
    accion: str,
    autor_email: str,
    mensaje_refinar: str = None,
):
    """Helper para que otros endpoints guarden snapshot."""
    if not dictamen_html:
        return
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html=dictamen_html,
        accion=accion,
        mensaje_refinar=mensaje_refinar,
        autor_email=autor_email,
    ))
    db.commit()
