from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.models.db import GlosaRecord
from app.models.schemas import AnalyticsResult
from app.domain.entities.glosa import GlosaEntity, EstadoGlosa
from app.domain.services.scoring import MotorScoring


class GlosaRepository:
    def __init__(self, db: Session):
        self.db = db
        self.scoring = MotorScoring()

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
        modelo_ia: Optional[str] = None,
        score: int = 0,
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
            modelo_ia=modelo_ia,
            score=score,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def actualizar_estado(
        self,
        glosa_id: int,
        nuevo_estado: str,
        responsable: Optional[str] = None,
    ) -> Optional[GlosaRecord]:
        glosa = self.obtener_por_id(glosa_id)
        if not glosa:
            return None
        
        try:
            estado_enum = EstadoGlosa[nuevo_estado.upper()]
        except KeyError:
            estado_enum = EstadoGlosa.RADICADA
        
        entity = self._to_entity(glosa)
        if entity.transicionar(estado_enum, responsable):
            glosa.estado = nuevo_estado
            glosa.responsable = responsable
            glosa.score = self.scoring.calcular_score(
                GlosaEntity(
                    valor_objetado=glosa.valor_objetado,
                    dias_restantes=glosa.dias_restantes,
                )
            )
            self.db.commit()
            self.db.refresh(glosa)
        return glosa

    def _to_entity(self, record: GlosaRecord) -> GlosaEntity:
        return GlosaEntity(
            id=record.id,
            eps=record.eps,
            paciente=record.paciente,
            factura=record.factura,
            codigo_glosa=record.codigo_glosa,
            valor_objetado=record.valor_objetado,
            valor_aceptado=record.valor_aceptado,
            etapa=record.etapa,
            estado=EstadoGlosa(record.estado.upper()) if record.estado else EstadoGlosa.RADICADA,
            dictamen=record.dictamen or "",
            dias_restantes=record.dias_restantes,
            score=record.score,
            modelo_ia=record.modelo_ia,
            responsable=record.responsable,
        )

    def listar(self, limit: int = 50, eps: Optional[str] = None) -> list[GlosaRecord]:
        q = self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc())
        if eps:
            q = q.filter(GlosaRecord.eps == eps.upper())
        return q.limit(limit).all()

    def obtener_por_id(self, glosa_id: int) -> Optional[GlosaRecord]:
        return self.db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()

    def alertas_proximas(self, dias_limite: int = 5) -> list[GlosaRecord]:
        return (
            self.db.query(GlosaRecord)
            .filter(
                GlosaRecord.dias_restantes <= dias_limite,
                GlosaRecord.dias_restantes > 0,
                GlosaRecord.estado != "LEVANTADA",
            )
            .order_by(GlosaRecord.dias_restantes.asc())
            .all()
        )

    def analytics(self) -> AnalyticsResult:
        stats = self.db.query(
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        ).first()

        total      = stats[0] or 0
        v_objetado = float(stats[1] or 0)
        v_aceptado = float(stats[2] or 0)
        v_recuperado = v_objetado - v_aceptado

        return AnalyticsResult(
            glosas_mes=total,
            valor_objetado_mes=v_objetado,
            valor_recuperado_mes=v_recuperado,
            tasa_exito_pct=round((v_recuperado / v_objetado * 100) if v_objetado > 0 else 0, 1),
        )

    def listar_todos(self) -> list[GlosaRecord]:
        return self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc()).all()
