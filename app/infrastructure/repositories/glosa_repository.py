import json
import logging
from typing import Optional, List
from sqlalchemy.orm import Session

from app.infrastructure.db.models import GlosaRecord, HistorialGlosaRecord

logger = logging.getLogger("glosa_repository")


class GlosaRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(
        self,
        eps: str,
        paciente: str,
        codigo_glosa: str,
        valor_objetado: float,
        valor_aceptado: float,
        etapa: str,
        estado: str = "RADICADA",
        dictamen: Optional[str] = None,
        dias_restantes: int = 0,
        responsable_id: Optional[int] = None,
        score: int = 0,
        prioridad: str = "BAJA",
        modelo_ia: Optional[str] = None,
        factura: str = "N/A",
        autorizacion: str = "N/A",
    ) -> GlosaRecord:
        glosa = GlosaRecord(
            eps=eps.upper(),
            paciente=paciente,
            codigo_glosa=codigo_glosa,
            valor_objetado=valor_objetado,
            valor_aceptado=valor_aceptado,
            etapa=etapa,
            estado=estado,
            dictamen=dictamen,
            dias_restantes=dias_restantes,
            responsable_id=responsable_id,
            score=score,
            prioridad=prioridad,
            modelo_ia=modelo_ia,
            factura=factura,
            autorizacion=autorizacion,
        )
        self.db.add(glosa)
        self.db.commit()
        self.db.refresh(glosa)
        logger.info(f"Glosa creada: {glosa.id} - EPS: {eps}")
        return glosa

    def obtener_por_id(self, glosa_id: int) -> Optional[GlosaRecord]:
        return self.db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()

    def listar(self, limit: int = 50, eps: Optional[str] = None, estado: Optional[str] = None) -> List[GlosaRecord]:
        query = self.db.query(GlosaRecord)
        if eps:
            query = query.filter(GlosaRecord.eps == eps.upper())
        if estado:
            query = query.filter(GlosaRecord.estado == estado)
        return query.order_by(GlosaRecord.creado_en.desc()).limit(limit).all()

    def actualizar_estado(self, glosa_id: int, nuevo_estado: str, usuario_id: Optional[int] = None, observacion: Optional[str] = None) -> Optional[GlosaRecord]:
        glosa = self.obtener_por_id(glosa_id)
        if not glosa:
            return None
        
        estado_anterior = glosa.estado
        
        historial = HistorialGlosaRecord(
            glosa_id=glosa_id,
            estado_anterior=estado_anterior,
            estado_nuevo=nuevo_estado,
            usuario_id=usuario_id,
            observacion=observacion,
        )
        self.db.add(historial)
        
        glosa.estado = nuevo_estado
        self.db.commit()
        self.db.refresh(glosa)
        logger.info(f"Glosa {glosa_id} cambió de {estado_anterior} a {nuevo_estado}")
        return glosa

    def actualizar(self, glosa_id: int, **kwargs) -> Optional[GlosaRecord]:
        glosa = self.obtener_por_id(glosa_id)
        if not glosa:
            return None
        
        for key, value in kwargs.items():
            if hasattr(glosa, key):
                setattr(glosa, key, value)
        
        self.db.commit()
        self.db.refresh(glosa)
        return glosa

    def alertas_proximas(self, dias_limite: int = 5) -> List[GlosaRecord]:
        return self.db.query(GlosaRecord).filter(
            GlosaRecord.dias_restantes <= dias_limite,
            GlosaRecord.estado.in_(["RADICADA", "EN_REVISION"]),
        ).order_by(GlosaRecord.dias_restantes.asc()).all()

    def obtener_todas_por_eps(self, eps: str) -> List[GlosaRecord]:
        return self.db.query(GlosaRecord).filter(GlosaRecord.eps == eps.upper()).all()

    def estadisticas(self, eps: Optional[str] = None) -> dict:
        from sqlalchemy import func
        
        query = self.db.query(GlosaRecord)
        if eps:
            query = query.filter(GlosaRecord.eps == eps.upper())
        
        total = query.count()
        rad = query.filter(GlosaRecord.estado == "RADICADA").count()
        rev = query.filter(GlosaRecord.estado == "EN_REVISION").count()
        resp = query.filter(GlosaRecord.estado == "RESPONDIDA").count()
        acept = query.filter(GlosaRecord.estado == "ACEPTADA").count()
        rech = query.filter(GlosaRecord.estado == "RECHAZADA").count()
        
        valor_total = query.with_entities(func.sum(GlosaRecord.valor_objetado)).scalar() or 0
        valor_recup = query.with_entities(func.sum(GlosaRecord.valor_aceptado)).scalar() or 0
        
        return {
            "total": total,
            "radicadas": rad,
            "en_revision": rev,
            "respondidas": resp,
            "aceptadas": acept,
            "rechazadas": rech,
            "valor_objetado_total": valor_total,
            "valor_recuperado_total": valor_recup,
            "tasa_exito": (acept / total * 100) if total > 0 else 0,
        }