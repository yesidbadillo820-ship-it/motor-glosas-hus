import json
import logging
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.infrastructure.db.models import ContratoRecord

logger = logging.getLogger("contrato_repository")


class ContratoRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(self, eps: str, detalles: str, version: int = 1) -> ContratoRecord:
        contrato = ContratoRecord(
            eps=eps.upper(),
            detalles=detalles,
            version=version,
            vigente=True,
        )
        self.db.add(contrato)
        self.db.commit()
        self.db.refresh(contrato)
        logger.info(f"Contrato creado: {eps} v{version}")
        return contrato

    def obtener(self, eps: str) -> Optional[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(
            and_(ContratoRecord.eps == eps.upper(), ContratoRecord.vigente == True)
        ).first()

    def obtener_version(self, eps: str, version: int) -> Optional[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(
            and_(ContratoRecord.eps == eps.upper(), ContratoRecord.version == version)
        ).first()

    def actualizar(self, eps: str, detalles: str) -> ContratoRecord:
        contrato_existente = self.obtener(eps)
        
        if contrato_existente:
            contrato_existente.vigente = False
            nueva_version = contrato_existente.version + 1
            
            nuevo_contrato = ContratoRecord(
                eps=eps.upper(),
                detalles=detalles,
                version=nueva_version,
                vigente=True,
            )
            self.db.add(nuevo_contrato)
            self.db.commit()
            self.db.refresh(nuevo_contrato)
            logger.info(f"Contrato actualizado: {eps} -> v{nueva_version}")
            return nuevo_contrato
        
        return self.crear(eps, detalles, version=1)

    def listar_todos(self) -> List[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(ContratoRecord.vigente == True).all()

    def como_dict(self) -> Dict[str, str]:
        contratos = self.listar_todos()
        return {c.eps: c.detalles for c in contratos}

    def historial_versiones(self, eps: str) -> List[ContratoRecord]:
        return self.db.query(ContratoRecord).filter(
            ContratoRecord.eps == eps.upper()
        ).order_by(ContratoRecord.version.desc()).all()

    def eliminar(self, eps: str) -> bool:
        contrato = self.obtener(eps)
        if contrato:
            contrato.vigente = False
            self.db.commit()
            return True
        return False