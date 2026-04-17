"""Operaciones administrativas peligrosas (reset de datos).

Requiere rol SUPER_ADMIN y confirmación explícita para todas las acciones.
Cada operación queda registrada en audit_log para trazabilidad.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.db import (
    UsuarioRecord,
    GlosaRecord,
    ConciliacionRecord,
    AuditLogRecord,
)
from app.api.deps import get_admin
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/admin", tags=["admin"])

# Frase de confirmación obligatoria en el body
CONFIRMACION_REQUERIDA = "CONFIRMAR-BORRADO-TOTAL"


class ResetDatosRequest(BaseModel):
    confirmar: str  # debe ser exactamente CONFIRMACION_REQUERIDA
    borrar_historial: bool = True
    borrar_conciliaciones: bool = True
    borrar_audit_log: bool = False


@router.post("/reset-datos")
def reset_datos(
    data: ResetDatosRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Borra datos transaccionales del sistema dejando intactos:
    - Usuarios
    - Contratos
    - Plantillas

    Solo SUPER_ADMIN. Requiere confirmación explícita en el body.
    """
    if data.confirmar != CONFIRMACION_REQUERIDA:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Para confirmar el borrado debes enviar el campo 'confirmar' con "
                f"el valor exacto: {CONFIRMACION_REQUERIDA}"
            ),
        )

    resumen = {"historial": 0, "conciliaciones": 0, "audit_log": 0}

    try:
        if data.borrar_conciliaciones:
            # Primero conciliaciones (referencian historial por FK)
            resumen["conciliaciones"] = db.query(ConciliacionRecord).delete(synchronize_session=False)

        if data.borrar_historial:
            resumen["historial"] = db.query(GlosaRecord).delete(synchronize_session=False)

        db.commit()

        # Registrar la acción en audit_log ANTES de borrarlo (si aplica)
        AuditRepository(db).registrar(
            usuario_email=current_user.email,
            usuario_rol=current_user.rol,
            accion="RESET_DATOS",
            tabla="multiple",
            detalle=(
                f"Borrado: historial={resumen['historial']}, "
                f"conciliaciones={resumen['conciliaciones']}, "
                f"audit_log_solicitado={data.borrar_audit_log}"
            ),
        )

        if data.borrar_audit_log:
            # Borramos TODO el audit_log excepto el registro recién creado (el del reset)
            # para mantener al menos la trazabilidad de este mismo reset.
            ultimo = db.query(AuditLogRecord).order_by(AuditLogRecord.id.desc()).first()
            q = db.query(AuditLogRecord)
            if ultimo:
                q = q.filter(AuditLogRecord.id != ultimo.id)
            resumen["audit_log"] = q.delete(synchronize_session=False)
            db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error al ejecutar el borrado: {str(e)}",
        )

    return {
        "message": "Datos transaccionales eliminados correctamente",
        "registros_borrados": resumen,
        "preservado": ["usuarios", "contratos", "plantillas"],
        "ejecutado_por": current_user.email,
    }


@router.get("/estadisticas")
def estadisticas_admin(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Cuenta rápida de registros por tabla (útil antes/después de un reset)."""
    return {
        "usuarios": db.query(UsuarioRecord).count(),
        "historial": db.query(GlosaRecord).count(),
        "conciliaciones": db.query(ConciliacionRecord).count(),
        "audit_log": db.query(AuditLogRecord).count(),
    }
