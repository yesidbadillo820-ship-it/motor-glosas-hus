from dataclasses import dataclass
from typing import Optional
import math

from app.domain.entities.glosa import GlosaEntity


@dataclass
class PesosScoring:
    peso_valor: float = 0.40
    peso_probabilidad: float = 0.35
    peso_urgencia: float = 0.25


class MotorScoring:
    def __init__(self, pesos: PesosScoring = None):
        self.pesos = pesos or PesosScoring()
    
    def calcular_score(self, glosa: GlosaEntity, probabilidad_recuperacion: float = 0.8) -> int:
        valor = getattr(glosa, "valor_objetado", 0.0)
        dias_restantes = getattr(glosa, "dias_restantes", 0)
        
        score_valor = self._normalizar_valor(valor)
        score_probabilidad = probabilidad_recuperacion * 100
        score_urgencia = self._normalizar_urgencia(dias_restantes)
        
        score_total = (
            (score_valor * self.pesos.peso_valor) +
            (score_probabilidad * self.pesos.peso_probabilidad) +
            (score_urgencia * self.pesos.peso_urgencia)
        )
        
        return int(min(100, max(0, score_total)))
    
    def _normalizar_valor(self, valor: float) -> float:
        if valor <= 0:
            return 0.0
        log_valor = math.log10(max(1, valor))
        return min(100, log_valor * 10)
    
    def _normalizar_urgencia(self, dias_restantes: int) -> float:
        if dias_restantes <= 0:
            return 100.0
        elif dias_restantes >= 30:
            return 0.0
        else:
            return ((30 - dias_restantes) / 30) * 100
    
    def ordenar_por_prioridad(self, glosas: list[GlosaEntity]) -> list[GlosaEntity]:
        def get_score(g: GlosaEntity) -> int:
            return getattr(g, "score", 0)
        return sorted(glosas, key=get_score, reverse=True)
    
    def clasificar_urgencia(self, glosa: GlosaEntity) -> str:
        score = self.calcular_score(glosa)
        dias = getattr(glosa, "dias_restantes", 0)
        
        if dias <= 0:
            return "VENCIDA"
        elif score >= 70:
            return "URGENTE"
        elif score >= 40:
            return "MEDIA"
        else:
            return "BAJA"