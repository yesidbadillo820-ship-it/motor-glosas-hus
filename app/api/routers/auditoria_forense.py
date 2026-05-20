"""Router de auditoría forense — búsqueda por IP e IPs frecuentes."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import AuditLogRecord, UsuarioRecord

router = APIRouter(prefix="/auditoria-forense", tags=["auditoria-forense"])


@router.get("/buscar-por-ip")
def buscar_por_ip(
    ip: str = Query(...),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    _usuario: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Retorna todos los eventos de auditoría asociados a una IP."""
    registros = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.ip == ip)
        .order_by(AuditLogRecord.timestamp.desc())
        .all()
    )

    total_eventos = len(registros)
    primer_evento_en = None
    usuarios_set: list[str] = []
    acciones_set: list[str] = []

    for r in registros:
        if r.usuario_email and r.usuario_email not in usuarios_set:
            usuarios_set.append(r.usuario_email)
        if r.accion and r.accion not in acciones_set:
            acciones_set.append(r.accion)
        if primer_evento_en is None or (r.timestamp and r.timestamp < primer_evento_en):
            primer_evento_en = r.timestamp

    usuarios_distintos = sorted(usuarios_set)
    acciones_distintas = sorted(acciones_set)

    items = [
        {
            "usuario_email": r.usuario_email,
            "accion": r.accion,
            "tabla": r.tabla,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "ip": r.ip,
            "detalle": r.detalle,
        }
        for r in registros[:limit]
    ]

    return {
        "total_eventos": total_eventos,
        "usuarios_distintos": usuarios_distintos,
        "acciones_distintas": acciones_distintas,
        "primer_evento_en": primer_evento_en.isoformat() if primer_evento_en else None,
        "items": items,
        "ip": ip,
        "limit": limit,
    }


@router.get("/ips-frecuentes")
def ips_frecuentes(
    dias: int = Query(30),
    top: int = Query(10),
    db: Session = Depends(get_db),
    _usuario: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Retorna las IPs con más eventos en los últimos N días."""
    desde = ahora_utc() - timedelta(days=dias)

    rows = (
        db.query(
            AuditLogRecord.ip,
            func.count(AuditLogRecord.id).label("eventos"),
            func.count(func.distinct(AuditLogRecord.usuario_email)).label("usuarios_distintos"),
        )
        .filter(
            AuditLogRecord.ip.isnot(None),
            AuditLogRecord.timestamp >= desde,
        )
        .group_by(AuditLogRecord.ip)
        .order_by(func.count(AuditLogRecord.id).desc())
        .all()
    )

    total_ips_unicas = len(rows)
    items = [
        {
            "ip": row.ip,
            "eventos": row.eventos,
            "usuarios_distintos": row.usuarios_distintos,
        }
        for row in rows[:top]
    ]

    return {
        "items": items,
        "total_ips_unicas": total_ips_unicas,
    }
