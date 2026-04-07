from app.domain.entities import Glosa
from app.domain.value_objects import ScoringGlosa


class ScoringService:
    def __init__(
        self,
        peso_valor: float = 0.4,
        peso_probabilidad: float = 0.3,
        peso_urgencia: float = 0.3,
    ):
        self.peso_valor = peso_valor
        self.peso_probabilidad = peso_probabilidad
        self.peso_urgencia = peso_urgencia
    
    def calcular_score(self, glosa: Glosa) -> ScoringGlosa:
        score_valor = self._normalizar_valor(glosa.valor_objetado)
        score_prob = self._calcular_probabilidad(glosa)
        score_urgencia = self._normalizar_urgencia(glosa.dias_restantes)
        
        score_total = int(
            (score_valor * self.peso_valor) +
            (score_prob * self.peso_probabilidad) +
            (score_urgencia * self.peso_urgencia)
        )
        
        prioridad = self._determinar_prioridad(score_total)
        valor_recuperable = glosa.valor_objetado * score_prob
        
        return ScoringGlosa(
            score=score_total,
            prioridad=prioridad,
            valor_recuperable_estimado=valor_recuperable,
            probabilidad_recuperacion=score_prob
        )
    
    def _normalizar_valor(self, valor: float) -> float:
        if valor >= 5000000:
            return 100
        elif valor >= 2000000:
            return 80
        elif valor >= 1000000:
            return 60
        elif valor >= 500000:
            return 40
        elif valor >= 100000:
            return 20
        return 10
    
    def _normalizar_urgencia(self, dias: int) -> float:
        if dias <= 0:
            return 100
        elif dias <= 3:
            return 80
        elif dias <= 7:
            return 60
        elif dias <= 15:
            return 40
        elif dias <= 30:
            return 20
        return 10
    
    def _calcular_probabilidad(self, glosa: Glosa) -> float:
        probabilidad = 0.7
        
        if glosa.es_extemporanea:
            probabilidad -= 0.3
        
        if glosa.dias_restantes <= 0:
            probabilidad -= 0.2
        
        eps = glosa.eps.upper()
        if eps in ["COOSALUD", "COMPENSAR"]:
            probabilidad += 0.1
        elif eps in ["NUEVA EPS", "PPL"]:
            probabilidad -= 0.1
        
        return max(0.1, min(0.95, probabilidad))
    
    def _determinar_prioridad(self, score: int) -> str:
        if score >= 80:
            return "CRITICA"
        elif score >= 60:
            return "ALTA"
        elif score >= 40:
            return "MEDIA"
        return "BAJA"
