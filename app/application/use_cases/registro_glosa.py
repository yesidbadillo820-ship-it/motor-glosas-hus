from dataclasses import dataclass
from typing import Optional
from datetime import date, datetime
from app.domain.entities.glosa import Glosa, EstadoGlosa, Etapa
from app.domain.value_objects.monto import Monto


@dataclass
class ResultadoRegistro:
    glosa_id: int
    eps: str
    paciente: str
    valor_objetado: float
    estado: str
    score: int


class RegistroGlosaUseCase:
    def __init__(self, repositorio=None):
        self.repositorio = repositorio

    def ejecutar(
        self,
        glosa: Glosa,
    ) -> ResultadoRegistro:
        if not glosa.codigo_glosa:
            glosa.codigo_glosa = "PENDIENTE"
        
        if not glosa.estado:
            glosa.estado = EstadoGlosa.RADICADA
        
        from app.domain.services.scoring import SCORING_DEFAULT
        score = SCORING_DEFAULT.calcular(glosa).total
        glosa.score = score
        
        glosa_id = self._persistir(glosa)
        
        return ResultadoRegistro(
            glosa_id=glosa_id,
            eps=glosa.eps,
            paciente=glosa.paciente,
            valor_objetado=glosa.valor_objetado,
            estado=glosa.estado.value,
            score=score,
        )

    def _persistir(self, glosa: Glosa) -> int:
        from app.database import SessionLocal
        from app.models.db import GlosaRecord
        
        db = SessionLocal()
        try:
            record = GlosaRecord(
                eps=glosa.eps.upper(),
                paciente=glosa.paciente,
                factura=glosa.factura,
                codigo_glosa=glosa.codigo_glosa,
                valor_objetado=glosa.valor_objetado,
                valor_aceptado=glosa.valor_aceptado,
                etapa=glosa.etapa.value if hasattr(glosa.etapa, 'value') else str(glosa.etapa),
                estado=glosa.estado.value if hasattr(glosa.estado, 'value') else str(glosa.estado),
                dictamen=glosa.dictamen,
                dias_restantes=glosa.dias_restantes,
                modelo_ia=glosa.modelo_ia,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        finally:
            db.close()