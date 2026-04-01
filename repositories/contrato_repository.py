from sqlalchemy.orm import Session
from models.db import ContratoRecord
from models.schemas import ContratoInput


class ContratoRepository:

    def __init__(self, db: Session):
        self.db = db

    def listar(self) -> list[ContratoRecord]:
        return self.db.query(ContratoRecord).order_by(ContratoRecord.eps).all()

    def obtener(self, eps: str) -> ContratoRecord | None:
        return self.db.query(ContratoRecord).filter(
            ContratoRecord.eps == eps.upper()
        ).first()

    def como_dict(self) -> dict[str, str]:
        return {c.eps: c.detalles for c in self.listar()}

    def upsert(self, data: ContratoInput) -> ContratoRecord:
        existente = self.obtener(data.eps)
        if existente:
            existente.detalles = data.detalles
        else:
            existente = ContratoRecord(eps=data.eps.upper(), detalles=data.detalles)
            self.db.add(existente)
        self.db.commit()
        self.db.refresh(existente)
        return existente

    def eliminar(self, eps: str) -> bool:
        record = self.obtener(eps)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
