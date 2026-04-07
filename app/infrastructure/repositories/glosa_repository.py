from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.infrastructure.db.models import GlosaRecord
from app.domain.entities import Glosa, EstadoGlosa


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
        estado: str,
        dictamen: str,
        dias_restantes: int,
        dias_habiles: int = 0,
        es_extemporanea: bool = False,
        score: int = 0,
        prioridad: str = "BAJA",
        modelo_ia: Optional[str] = None,
        responsable_id: Optional[int] = None,
        observaciones: str = "",
        fecha_radicacion: Optional[datetime] = None,
        fecha_recepcion: Optional[datetime] = None,
    ) -> GlosaRecord:
        record = GlosaRecord(
            eps=eps,
            paciente=paciente,
            codigo_glosa=codigo_glosa,
            valor_objetado=valor_objetado,
            valor_aceptado=valor_aceptado,
            etapa=etapa,
            estado=estado,
            dictamen=dictamen,
            dias_restantes=dias_restantes,
            dias_habiles=dias_habiles,
            es_extemporanea=es_extemporanea,
            score=score,
            prioridad=prioridad,
            modelo_ia=modelo_ia,
            responsable_id=responsable_id,
            observaciones=observaciones,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def listar(
        self, limit: int = 50, eps: Optional[str] = None, 
        estado: Optional[str] = None, prioridad: Optional[str] = None
    ) -> List[GlosaRecord]:
        q = self.db.query(GlosaRecord).order_by(GlosaRecord.created_at.desc())
        if eps:
            q = q.filter(GlosaRecord.eps == eps.upper())
        if estado:
            q = q.filter(GlosaRecord.estado == estado.upper())
        if prioridad:
            q = q.filter(GlosaRecord.prioridad == prioridad.upper())
        return q.limit(limit).all()

    def obtener_por_id(self, glosa_id: int) -> Optional[GlosaRecord]:
        return self.db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()

    def actualizar_estado(
        self, glosa_id: int, nuevo_estado: str, responsable_id: int = None
    ) -> Optional[GlosaRecord]:
        glosa = self.obtener_por_id(glosa_id)
        if glosa:
            glosa.estado = nuevo_estado
            glosa.fecha_estado = datetime.now()
            glosa.responsable_id = responsable_id
            self.db.commit()
            self.db.refresh(glosa)
        return glosa

    def alertas_proximas(self, dias_limite: int = 5) -> List[GlosaRecord]:
        return (
            self.db.query(GlosaRecord)
            .filter(
                GlosaRecord.dias_restantes <= dias_limite,
                GlosaRecord.dias_restantes > 0,
                GlosaRecord.estado.notin_(["ACEPTADA", "RECHAZADA", "CERRADA"]),
            )
            .order_by(GlosaRecord.dias_restantes.asc())
            .all()
        )

    def listar_vencidas(self) -> List[GlosaRecord]:
        return (
            self.db.query(GlosaRecord)
            .filter(
                GlosaRecord.dias_restantes <= 0,
                GlosaRecord.estado.notin_(["ACEPTADA", "RECHAZADA", "CERRADA"]),
            )
            .all()
        )

    def metrics(self) -> dict:
        total = self.db.query(func.count(GlosaRecord.id)).scalar() or 0
        por_estado = self.db.query(
            GlosaRecord.estado,
            func.count(GlosaRecord.id)
        ).group_by(GlosaRecord.estado).all()
        
        por_eps = self.db.query(
            GlosaRecord.eps,
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado)
        ).group_by(GlosaRecord.eps).all()
        
        valor_total = self.db.query(func.sum(GlosaRecord.valor_objetado)).scalar() or 0
        valor_recuperado = self.db.query(func.sum(GlosaRecord.valor_aceptado)).scalar() or 0
        
        return {
            "total": total,
            "por_estado": {e: c for e, c in por_estado},
            "por_eps": [
                {"eps": e, "count": c, "valor": float(v or 0)} 
                for e, c, v in por_eps
            ],
            "valor_total": float(valor_total),
            "valor_recuperado": float(valor_recuperado),
            "tasa_recuperacion": round((valor_recuperado / valor_total * 100) if valor_total > 0 else 0, 2)
        }
