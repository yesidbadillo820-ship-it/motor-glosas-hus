from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.infrastructure.db.models import ContratoRecord


class ContratoRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(self, eps: str, detalles: str, version: int = 1) -> ContratoRecord:
        record = ContratoRecord(
            eps=eps.upper(),
            detalles=detalles,
            version=version,
            fecha_inicio=datetime.now(),
            activo=True,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def obtener(self, eps: str) -> Optional[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(
            ContratoRecord.eps == eps.upper(),
            ContratoRecord.activo == True
        ).first()

    def obtener_todos(self) -> list[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(
            ContratoRecord.activo == True
        ).all()

    def como_dict(self) -> dict:
        contratos = self.obtener_todos()
        return {c.eps: c.detalles for c in contratos}

    def crear_version(self, eps: str, detalles: str) -> ContratoRecord:
        existente = self.obtener(eps)
        if existente:
            existente.activo = False
            version_nueva = existente.version + 1
        else:
            version_nueva = 1
        
        return self.crear(eps, detalles, version_nueva)

    def listar_historial(self, eps: str) -> list[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(
            ContratoRecord.eps == eps.upper()
        ).order_by(ContratoRecord.version.desc()).all()
