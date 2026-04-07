from typing import Optional
from datetime import datetime
from app.domain.entities import Glosa, EstadoGlosa
from app.domain.services.scoring import ScoringService
from app.domain.services.workflow import WorkflowEngine
from app.domain.services import (
    MotorReglas, ReglaExtemporaneidad, ReglaContrato, 
    ReglaCobertura, ReglaValorMinimo, ReglaUrgencia
)


class AnalisisGlosaUseCase:
    def __init__(self):
        self.scoring_service = ScoringService()
        self.workflow = WorkflowEngine()
    
    def ejecutar(
        self,
        eps: str,
        etapa: str,
        fecha_radicacion: Optional[datetime],
        fecha_recepcion: Optional[datetime],
        valor_aceptado: float,
        tabla_excel: str,
        contratos_db: dict,
        contexto_pdf: str = "",
    ) -> dict:
        glosa = Glosa(
            eps=eps,
            etapa=etapa,
            valor_aceptado=valor_aceptado,
            fecha_radicacion=fecha_radicacion,
            fecha_recepcion=fecha_recepcion,
        )
        
        if fecha_radicacion and fecha_recepcion:
            glosa.dias_habiles = self._calcular_dias(fecha_radicacion, fecha_recepcion)
            glosa.es_extemporanea = glosa.dias_habiles > 20
            glosa.dias_restantes = max(0, 20 - glosa.dias_habiles)
        
        scoring = self.scoring_service.calcular_score(glosa)
        
        motor = MotorReglas([
            ReglaExtemporaneidad(),
            ReglaContrato(contratos_db),
            ReglaCobertura(),
            ReglaValorMinimo(),
            ReglaUrgencia(),
        ])
        
        resultados_reglas = motor.evaluar(glosa)
        
        tiene_extemporanea = any(
            r.regla_id == "RE001" and not r.cumple for r in resultados_reglas
        )
        
        if tiene_extemporanea:
            glosa.estado = EstadoGlosa.RADICADA.value
        else:
            glosa.estado = EstadoGlosa.EN_REVISION.value
        
        return {
            "glosa": glosa,
            "scoring": scoring,
            "resultados_reglas": resultados_reglas,
            "tiene_fallas_criticas": motor.tiene_fallas_criticas(resultados_reglas),
        }
    
    def _calcular_dias(self, f1, f2) -> int:
        from datetime import timedelta
        try:
            delta = f2 - f1
            dias_habiles = 0
            current = f1
            while current < f2:
                current += timedelta(days=1)
                if current.weekday() < 5:
                    dias_habiles += 1
            return dias_habiles
        except:
            return 0


class GestionarWorkflowUseCase:
    def __init__(self):
        self.workflow = WorkflowEngine()
    
    def transicionar(self, glosa: Glosa, nuevo_estado: str, responsable_id: int) -> Glosa:
        return self.workflow.transicionar(glosa, nuevo_estado, responsable_id)
    
    def verificar_permiso(self, estado_actual: str, nuevo_estado: str) -> bool:
        return self.workflow.puede_transicionar(estado_actual, nuevo_estado)
    
    def obtener_siguiente(self, estado_actual: str) -> Optional[str]:
        return self.workflow.obtener_siguiente_estado(estado_actual)


class CalcularScoringUseCase:
    def __init__(self):
        self.scoring_service = ScoringService()
    
    def ejecutar(self, glosa: Glosa) -> dict:
        scoring = self.scoring_service.calcular_score(glosa)
        return {
            "score": scoring.score,
            "prioridad": scoring.prioridad,
            "valor_recuperable": scoring.valor_recuperable_estimado,
            "probabilidad": scoring.probabilidad_recuperacion,
            "categoria": scoring.categoria,
        }
