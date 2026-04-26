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


@router.get("/facetas")
def facetas_audit_log(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R87 P2: facetas únicas del audit log para construir filtros UI.

    Devuelve los valores DISTINCT no-nulos de accion, tabla y
    usuario_email. Útil para que el frontend renderice <select>
    poblados con valores reales en lugar de inputs libres.

    No filtra por fecha — refleja el universo histórico para evitar
    que el dropdown se "encoja" si no hay eventos recientes con cierto
    valor.
    """
    from app.models.db import AuditLogRecord

    def _distinct(col):
        rows = (
            db.query(col)
            .filter(col.isnot(None))
            .distinct()
            .order_by(col.asc())
            .all()
        )
        return [r[0] for r in rows if r[0]]

    return {
        "acciones": _distinct(AuditLogRecord.accion),
        "tablas": _distinct(AuditLogRecord.tabla),
        "usuarios": _distinct(AuditLogRecord.usuario_email),
        "roles": _distinct(AuditLogRecord.usuario_rol),
    }


@router.get("/stats")
def stats_audit_log(
    dias: int = Query(30, ge=1, le=365, description="Ventana en días"),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R87 P1: resumen agregado del audit log para dashboards.

    Devuelve:
      - total_eventos en la ventana
      - top_10_usuarios por cantidad de eventos
      - top_10_acciones más comunes
      - top_10_tablas más afectadas
      - eventos_por_dia (últimos N días)

    Útil para que el coordinador identifique de un vistazo qué
    está pasando en el sistema sin tener que paginar audit log.
    """
    from datetime import timedelta

    from sqlalchemy import func as sa_func

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    corte = ahora_utc() - timedelta(days=int(dias))
    base = db.query(AuditLogRecord).filter(AuditLogRecord.timestamp >= corte)

    total = base.count()

    top_usuarios = (
        db.query(
            AuditLogRecord.usuario_email,
            sa_func.count(AuditLogRecord.id).label("n"),
        )
        .filter(AuditLogRecord.timestamp >= corte)
        .filter(AuditLogRecord.usuario_email.isnot(None))
        .group_by(AuditLogRecord.usuario_email)
        .order_by(sa_func.count(AuditLogRecord.id).desc())
        .limit(10)
        .all()
    )

    top_acciones = (
        db.query(
            AuditLogRecord.accion,
            sa_func.count(AuditLogRecord.id).label("n"),
        )
        .filter(AuditLogRecord.timestamp >= corte)
        .filter(AuditLogRecord.accion.isnot(None))
        .group_by(AuditLogRecord.accion)
        .order_by(sa_func.count(AuditLogRecord.id).desc())
        .limit(10)
        .all()
    )

    top_tablas = (
        db.query(
            AuditLogRecord.tabla,
            sa_func.count(AuditLogRecord.id).label("n"),
        )
        .filter(AuditLogRecord.timestamp >= corte)
        .filter(AuditLogRecord.tabla.isnot(None))
        .group_by(AuditLogRecord.tabla)
        .order_by(sa_func.count(AuditLogRecord.id).desc())
        .limit(10)
        .all()
    )

    # Distribución por día — agrupando en Python para portabilidad
    # SQLite/PostgreSQL (date() funciona distinto en cada motor).
    eventos_por_dia: dict[str, int] = {}
    for r in base.all():
        if r.timestamp:
            k = r.timestamp.date().isoformat()
            eventos_por_dia[k] = eventos_por_dia.get(k, 0) + 1

    return {
        "ventana_dias": int(dias),
        "total_eventos": total,
        "top_10_usuarios": [{"usuario": u, "eventos": n} for u, n in top_usuarios],
        "top_10_acciones": [{"accion": a, "eventos": n} for a, n in top_acciones],
        "top_10_tablas": [{"tabla": t, "eventos": n} for t, n in top_tablas],
        "eventos_por_dia": [
            {"fecha": k, "eventos": v}
            for k, v in sorted(eventos_por_dia.items())
        ],
    }


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
