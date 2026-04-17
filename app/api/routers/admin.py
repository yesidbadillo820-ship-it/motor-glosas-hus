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


@router.post("/backfill-historial")
def backfill_historial(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Rellena los campos nuevos (cups_servicio, servicio_descripcion,
    concepto_glosa, codigo_respuesta, texto_glosa_original) en glosas
    antiguas que fueron creadas antes de que existieran esas columnas.

    Solo toca glosas con al menos UN campo nuevo vacío. No modifica el
    dictamen ni los valores monetarios. Solo SUPER_ADMIN.
    """
    import re
    from app.main import _concepto_glosa, _extraer_cups_servicio

    # Query: glosas con al menos un campo nuevo en NULL
    glosas = db.query(GlosaRecord).filter(
        (GlosaRecord.concepto_glosa.is_(None)) |
        (GlosaRecord.codigo_respuesta.is_(None)) |
        (GlosaRecord.cups_servicio.is_(None)) |
        (GlosaRecord.servicio_descripcion.is_(None))
    ).all()

    actualizadas = 0
    for g in glosas:
        cambios = False

        # 1. Concepto por código (siempre derivable si hay código)
        if not g.concepto_glosa and g.codigo_glosa:
            g.concepto_glosa = _concepto_glosa(g.codigo_glosa)
            cambios = True

        # 2. CUPS y servicio desde el texto_glosa_original o desde el dictamen
        if (not g.cups_servicio or not g.servicio_descripcion):
            fuente = g.texto_glosa_original or ""
            if not fuente and g.dictamen:
                # Del dictamen HTML quitamos tags y tomamos texto
                fuente = re.sub(r"<[^>]+>", " ", g.dictamen)
            cups, servicio = _extraer_cups_servicio(fuente, "")
            if not g.cups_servicio and cups:
                g.cups_servicio = cups
                cambios = True
            if not g.servicio_descripcion and servicio:
                g.servicio_descripcion = servicio[:400]
                cambios = True

        # 3. Código de respuesta: extraer del dictamen (ej. "RE9901") o de un
        #    tipo guardado ("RESPUESTA RE9901")
        if not g.codigo_respuesta and g.dictamen:
            m = re.search(r"\bRE\d{4}\b", g.dictamen)
            if m:
                g.codigo_respuesta = m.group(0)
                cambios = True

        if cambios:
            actualizadas += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar backfill: {e}")

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="BACKFILL_HISTORIAL",
        tabla="historial",
        detalle=f"Glosas actualizadas: {actualizadas} de {len(glosas)} con campos nulos",
    )

    return {
        "message": "Backfill completado",
        "glosas_con_campos_nulos": len(glosas),
        "glosas_actualizadas": actualizadas,
        "ejecutado_por": current_user.email,
    }
