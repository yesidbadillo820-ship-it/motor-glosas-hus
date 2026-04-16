from typing import Optional, List
from sqlalchemy.orm import Session
from app.models.db import PlantillaRecord

class PlantillaRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(self, nombre: str, codigo: str, tipo: str, eps: str, plantilla: str) -> PlantillaRecord:
        record = PlantillaRecord(
            nombre=nombre,
            codigo=codigo,
            tipo=tipo,
            eps=eps,
            plantilla=plantilla,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def listar(self, activa_only: bool = True) -> List[PlantillaRecord]:
        query = self.db.query(PlantillaRecord)
        if activa_only:
            query = query.filter(PlantillaRecord.activa == 1)
        return query.order_by(PlantillaRecord.nombre).all()

    def obtener_por_id(self, id: int) -> Optional[PlantillaRecord]:
        return self.db.query(PlantillaRecord).filter(PlantillaRecord.id == id).first()

    def obtener_por_codigo(self, codigo: str) -> Optional[PlantillaRecord]:
        return self.db.query(PlantillaRecord).filter(
            PlantillaRecord.codigo == codigo.upper(),
            PlantillaRecord.activa == 1
        ).first()

    def actualizar(self, id: int, nombre: str = None, plantilla: str = None, activa: int = None) -> Optional[PlantillaRecord]:
        record = self.obtener_por_id(id)
        if record:
            if nombre: record.nombre = nombre
            if plantilla: record.plantilla = plantilla
            if activa is not None: record.activa = activa
            self.db.commit()
            self.db.refresh(record)
        return record

    def eliminar(self, id: int) -> bool:
        record = self.obtener_por_id(id)
        if record:
            record.activa = 0
            self.db.commit()
            return True
        return False

    def get_plantilla_eps(self, eps: str, tipo: str) -> Optional[str]:
        """Busca plantilla específica para EPS+tipo, luego fallback por tipo, luego TODAS."""
        if not eps:
            return None
        
        eps_upper = eps.upper()
        
        # 1. Plantilla exacta EPS + tipo
        rec = self.db.query(PlantillaRecord).filter(
            PlantillaRecord.eps.ilike(f"%{eps_upper}%"),
            PlantillaRecord.tipo == tipo,
            PlantillaRecord.activa == 1
        ).first()
        if rec:
            return rec.plantilla
        
        # 2. Fallback: plantilla genérica para el tipo (sin EPS específica)
        rec = self.db.query(PlantillaRecord).filter(
            PlantillaRecord.eps == "",
            PlantillaRecord.tipo == tipo,
            PlantillaRecord.activa == 1
        ).first()
        if rec:
            return rec.plantilla
        
        # 3. Fallback global
        rec = self.db.query(PlantillaRecord).filter(
            PlantillaRecord.tipo == "FALLBACK",
            PlantillaRecord.activa == 1
        ).first()
        return rec.plantilla if rec else None
