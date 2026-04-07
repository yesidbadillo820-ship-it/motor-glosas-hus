import json
import logging
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from app.infrastructure.db.models import ReglaRecord

logger = logging.getLogger("regla_repository")


class ReglaRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(
        self,
        nombre: str,
        codigo: str,
        descripcion: str,
        parametros: Dict = None,
    ) -> ReglaRecord:
        regla = ReglaRecord(
            nombre=nombre,
            codigo=codigo,
            descripcion=descripcion,
            parametros=json.dumps(parametros or {}),
            activa=True,
            version=1,
        )
        self.db.add(regla)
        self.db.commit()
        self.db.refresh(regla)
        logger.info(f"Regla creada: {nombre} - código: {codigo}")
        return regla

    def obtener(self, nombre: str) -> Optional[ReglaRecord]:
        return self.db.query(ReglaRecord).filter(ReglaRecord.nombre == nombre).first()

    def obtener_por_codigo(self, codigo: str) -> Optional[ReglaRecord]:
        return self.db.query(ReglaRecord).filter(ReglaRecord.codigo == codigo).first()

    def listar_activas(self) -> List[ReglaRecord]:
        return self.db.query(ReglaRecord).filter(ReglaRecord.activa == True).all()

    def actualizar(self, nombre: str, descripcion: str = None, parametros: Dict = None) -> Optional[ReglaRecord]:
        regla = self.obtener(nombre)
        if not regla:
            return None
        
        if descripcion:
            regla.descripcion = descripcion
        if parametros:
            regla.parametros = json.dumps(parametros)
        
        self.db.commit()
        self.db.refresh(regla)
        return regla

    def desactivar(self, nombre: str) -> bool:
        regla = self.obtener(nombre)
        if regla:
            regla.activa = False
            self.db.commit()
            return True
        return False

    def versionar(self, nombre: str, nueva_version: int = None) -> Optional[ReglaRecord]:
        regla = self.obtener(nombre)
        if not regla:
            return None
        
        nueva_ver = (nueva_version or regla.version + 1)
        
        nueva_regla = ReglaRecord(
            nombre=regla.nombre,
            codigo=regla.codigo,
            descripcion=regla.descripcion,
            parametros=regla.parametros,
            activa=regla.activa,
            version=nueva_ver,
        )
        self.db.add(nueva_regla)
        self.db.commit()
        self.db.refresh(nueva_regla)
        return nueva_regla