from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.db import UsuarioRecord
from app.repositories.audit_repository import AuditRepository
from app.api.deps import get_coordinador_o_admin

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/")
def listar_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    usuario_email: Optional[str] = None,
    accion: Optional[str] = None,
    tabla: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    repo = AuditRepository(db)
    resultado = repo.listar(page=page, per_page=per_page,
                            usuario_email=usuario_email, accion=accion, tabla=tabla)
    return {
        "items": [
            {"id": r.id,
             "timestamp": r.timestamp.isoformat() if r.timestamp else None,
             "usuario_email": r.usuario_email, "usuario_rol": r.usuario_rol,
             "accion": r.accion, "tabla": r.tabla, "registro_id": r.registro_id,
             "campo": r.campo, "valor_anterior": r.valor_anterior,
             "valor_nuevo": r.valor_nuevo, "detalle": r.detalle, "ip": r.ip}
            for r in resultado["items"]
        ],
        "total": resultado["total"], "page": resultado["page"],
        "per_page": resultado["per_page"], "pages": resultado["pages"],
    }


@router.get("/glosa/{glosa_id}")
def historial_cambios_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    logs = AuditRepository(db).por_registro("glosas", glosa_id)
    return [
        {"id": r.id,
         "timestamp": r.timestamp.isoformat() if r.timestamp else None,
         "usuario_email": r.usuario_email, "accion": r.accion,
         "campo": r.campo, "valor_anterior": r.valor_anterior,
         "valor_nuevo": r.valor_nuevo, "detalle": r.detalle}
        for r in logs
    ]
