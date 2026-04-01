from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from models.db import GlosaRecord
from models.schemas import AnalyticsResult

class GlosaRepository:
    def __init__(self, db: Session):
        self.db = db

    def analytics(self) -> AnalyticsResult:
        stats = self.db.query(
            func.count(GlosaRecord.id),
            func.sum(GlosaRecord.valor_objetado),
            func.sum(GlosaRecord.valor_aceptado),
        ).first()
        
        total = stats[0] or 0
        v_obj = float(stats[1] or 0)
        v_ace = float(stats[2] or 0)
        v_rec = v_obj - v_ace
        
        return AnalyticsResult(
            glosas_mes=total,
            valor_objetado_mes=v_obj,
            valor_recuperado_mes=v_rec,
            tasa_exito_pct=round((v_rec / v_obj * 100) if v_obj > 0 else 0, 1)
        )

    def listar(self, limit: int = 50, eps: str = None):
        q = self.db.query(GlosaRecord).order_by(GlosaRecord.creado_en.desc())
        if eps:
            q = q.filter(GlosaRecord.eps == eps.upper())
        return q.limit(limit).all()
