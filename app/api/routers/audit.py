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


@router.get("/export.csv")
def exportar_audit_csv(
    desde: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    accion: Optional[str] = None,
    tabla: Optional[str] = None,
    usuario: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R62 P1: descarga el audit log como CSV con filtros opcionales.

    Útil para auditorías regulatorias (Ley 1581/2012 Habeas Data,
    Res. 1995/1999 Historia Clínica) que exigen export en formato
    plano. StreamingResponse para no cargar todo en memoria en
    exports grandes.
    """
    import csv
    import io
    from datetime import datetime, timezone

    from fastapi.responses import StreamingResponse

    from app.models.db import AuditLogRecord

    q = db.query(AuditLogRecord)
    if accion:
        q = q.filter(AuditLogRecord.accion.ilike(f"%{accion}%"))
    if tabla:
        q = q.filter(AuditLogRecord.tabla == tabla)
    if usuario:
        q = q.filter(AuditLogRecord.usuario_email.ilike(f"%{usuario}%"))
    if desde:
        try:
            dt = datetime.strptime(desde, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            q = q.filter(AuditLogRecord.timestamp >= dt)
        except ValueError:
            pass
    if hasta:
        try:
            dt = datetime.strptime(hasta, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            q = q.filter(AuditLogRecord.timestamp <= dt)
        except ValueError:
            pass

    # Hard-cap de 50_000 filas — más que eso debería ir por extracción
    # directa de BD, no por endpoint web.
    q = q.order_by(AuditLogRecord.timestamp.desc()).limit(50_000)

    def _generar_csv():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "id", "timestamp", "usuario_email", "usuario_rol",
            "accion", "tabla", "registro_id", "campo",
            "valor_anterior", "valor_nuevo", "detalle", "ip",
        ])
        yield buffer.getvalue()
        buffer.seek(0); buffer.truncate(0)
        for r in q.all():
            writer.writerow([
                r.id,
                r.timestamp.isoformat() if r.timestamp else "",
                r.usuario_email or "",
                r.usuario_rol or "",
                r.accion or "",
                r.tabla or "",
                r.registro_id if r.registro_id is not None else "",
                r.campo or "",
                (r.valor_anterior or "")[:1000],
                (r.valor_nuevo or "")[:1000],
                (r.detalle or "")[:1000],
                r.ip or "",
            ])
            yield buffer.getvalue()
            buffer.seek(0); buffer.truncate(0)

    fname = f"audit-log-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        _generar_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
