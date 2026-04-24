"""Papelera con soft-delete y restauración dentro de 30 días."""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.database import get_db
from app.models.db import GlosaEliminadaRecord, GlosaRecord, UsuarioRecord
from app.api.deps import get_coordinador_o_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/papelera", tags=["papelera"])


def _glosa_a_dict(g: GlosaRecord) -> dict:
    """Dump de todos los campos del GlosaRecord a dict (para JSON)."""
    out = {}
    for col in inspect(g).mapper.column_attrs:
        val = getattr(g, col.key)
        if isinstance(val, datetime):
            val = val.isoformat()
        out[col.key] = val
    return out


@router.get("/")
def listar(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Lista glosas eliminadas que aún pueden restaurarse (< 30 días)."""
    corte = datetime.utcnow() - timedelta(days=30)
    q = (
        db.query(GlosaEliminadaRecord)
        .filter(GlosaEliminadaRecord.eliminado_en >= corte)
        .order_by(GlosaEliminadaRecord.eliminado_en.desc())
    )
    items = []
    for r in q.limit(500).all():
        try:
            snap = json.loads(r.snapshot_json)
        except Exception:
            snap = {}
        dias_restantes = 30 - (datetime.utcnow() - r.eliminado_en).days if r.eliminado_en else 30
        items.append({
            "id": r.id,
            "glosa_id_original": r.glosa_id_original,
            "eliminado_por": r.eliminado_por,
            "eliminado_en": r.eliminado_en.isoformat() if r.eliminado_en else None,
            "motivo": r.motivo,
            "dias_restantes_restaurar": max(0, dias_restantes),
            "eps": snap.get("eps"),
            "factura": snap.get("factura"),
            "codigo_glosa": snap.get("codigo_glosa"),
            "valor_objetado": snap.get("valor_objetado"),
            "paciente": snap.get("paciente"),
        })
    return items


@router.post("/{papelera_id}/restaurar")
def restaurar(
    papelera_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    r = db.query(GlosaEliminadaRecord).filter(GlosaEliminadaRecord.id == papelera_id).first()
    if not r:
        raise HTTPException(404, "Registro de papelera no encontrado")
    try:
        snap = json.loads(r.snapshot_json)
    except Exception:
        raise HTTPException(500, "Snapshot corrupto")

    # Convertir ISO strings de vuelta a datetime
    for campo in ("creado_en", "fecha_recepcion", "fecha_entrega",
                  "fecha_vencimiento", "fecha_radicacion_factura",
                  "fecha_documento_dgh", "fecha_decision_eps"):
        if isinstance(snap.get(campo), str):
            try:
                snap[campo] = datetime.fromisoformat(snap[campo])
            except Exception:
                snap[campo] = None

    snap.pop("id", None)  # dejar que el autoincrement asigne uno nuevo
    try:
        nueva = GlosaRecord(**{k: v for k, v in snap.items() if hasattr(GlosaRecord, k)})
        db.add(nueva)
        db.delete(r)
        db.commit()
        db.refresh(nueva)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error restaurando: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="RESTAURAR_GLOSA", tabla="historial",
        registro_id=nueva.id,
        detalle=f"Restaurada desde papelera #{papelera_id}",
    )
    return {"message": "Glosa restaurada", "nuevo_id": nueva.id}


@router.delete("/{papelera_id}")
def purgar(
    papelera_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Elimina DEFINITIVAMENTE el registro de la papelera."""
    r = db.query(GlosaEliminadaRecord).filter(GlosaEliminadaRecord.id == papelera_id).first()
    if not r:
        raise HTTPException(404, "No encontrado")
    db.delete(r)
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="PURGAR_PAPELERA", tabla="glosas_eliminadas",
        registro_id=papelera_id,
    )
    return {"message": "Purgado definitivamente"}


def mover_a_papelera(db: Session, glosa: GlosaRecord, eliminado_por: str, motivo: str = "") -> int:
    """Helper: mueve una glosa a la papelera antes de eliminarla del histórico."""
    snap = json.dumps(_glosa_a_dict(glosa), ensure_ascii=False, default=str)
    reg = GlosaEliminadaRecord(
        glosa_id_original=glosa.id,
        snapshot_json=snap,
        eliminado_por=eliminado_por,
        motivo=motivo[:300] if motivo else None,
    )
    db.add(reg)
    db.flush()
    return reg.id
