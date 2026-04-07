from typing import List, Optional, Dict
from app.domain.entities.contrato import Contrato
from app.database import SessionLocal
from app.models.db import ContratoRecord


class ContratoRepository:
    def guardar(self, contrato: Contrato) -> bool:
        db = SessionLocal()
        try:
            record = ContratoRecord(
                eps=contrato.eps.upper(),
                detalles=contrato.detalles,
            )
            db.merge(record)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def buscar_por_eps(self, eps: str) -> Optional[Contrato]:
        db = SessionLocal()
        try:
            record = db.query(ContratoRecord).filter(ContratoRecord.eps == eps.upper()).first()
            if not record:
                return None
            return self._to_entity(record)
        finally:
            db.close()

    def listar_todos(self) -> List[Contrato]:
        db = SessionLocal()
        try:
            records = db.query(ContratoRecord).all()
            return [self._to_entity(r) for r in records]
        finally:
            db.close()

    def obtener_dict(self) -> Dict[str, str]:
        db = SessionLocal()
        try:
            records = db.query(ContratoRecord).all()
            return {r.eps: r.detalles for r in records}
        finally:
            db.close()

    def eliminar(self, eps: str) -> bool:
        db = SessionLocal()
        try:
            record = db.query(ContratoRecord).filter(ContratoRecord.eps == eps.upper()).first()
            if record:
                db.delete(record)
                db.commit()
                return True
            return False
        finally:
            db.close()

    def _to_entity(self, record: ContratoRecord) -> Contrato:
        return Contrato(
            eps=record.eps,
            detalles=record.detalles,
        )