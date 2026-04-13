from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.db import AuditLogRecord


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def registrar(
        self,
        usuario_email: str,
        usuario_rol: str,
        accion: str,
        tabla: str,
        registro_id: Optional[int] = None,
        campo: Optional[str] = None,
        valor_anterior: Optional[str] = None,
        valor_nuevo: Optional[str] = None,
        detalle: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> AuditLogRecord:
        try:
            log = AuditLogRecord(
                usuario_email=usuario_email,
                usuario_rol=usuario_rol,
                accion=accion,
                tabla=tabla,
                registro_id=registro_id,
                campo=campo,
                valor_anterior=str(valor_anterior)[:500] if valor_anterior else None,
                valor_nuevo=str(valor_nuevo)[:500] if valor_nuevo else None,
                detalle=str(detalle)[:1000] if detalle else None,
                ip=ip,
            )
            self.db.add(log)
            self.db.commit()
            return log
        except Exception:
            self.db.rollback()
            return None

    def listar(self, page=1, per_page=50, usuario_email=None, accion=None, tabla=None) -> dict:
        q = self.db.query(AuditLogRecord).order_by(desc(AuditLogRecord.timestamp))
        if usuario_email:
            q = q.filter(AuditLogRecord.usuario_email == usuario_email)
        if accion:
            q = q.filter(AuditLogRecord.accion == accion.upper())
        if tabla:
            q = q.filter(AuditLogRecord.tabla == tabla.lower())
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return {"items": items, "total": total, "page": page,
                "per_page": per_page, "pages": (total + per_page - 1) // per_page}

    def por_registro(self, tabla: str, registro_id: int) -> list:
        return (self.db.query(AuditLogRecord)
                .filter(AuditLogRecord.tabla == tabla,
                        AuditLogRecord.registro_id == registro_id)
                .order_by(desc(AuditLogRecord.timestamp)).all())
