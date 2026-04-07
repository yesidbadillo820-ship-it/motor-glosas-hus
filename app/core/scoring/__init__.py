from datetime import datetime
from typing import Optional
from app.domain.value_objects import ResultadoScoring


class ScoringService:
    """
    Sistema de scoring para priorización de glosas.
    
    Fórmula:
    score = (valor * peso_valor) 
          + (probabilidad_recuperacion * peso_probabilidad)
          - (dias_vencimiento * peso_urgencia)
    """
    
    PESO_VALOR = 0.4
    PESO_PROBABILIDAD = 0.35
    PESO_URGENCIA = 0.25
    
    UMBRAL_ALTA = 70
    UMBRAL_MEDIA = 40
    
    def calcular(
        self,
        valor_objetado: float,
        probabilidad_recuperacion: float,
        dias_restantes: int,
        estado: str = "RADICADA",
    ) -> ResultadoScoring:
        
        base_value = valor_objetado / 1000000
        
        value_score = base_value * self.PESO_VALOR * 100
        probability_score = probabilidad_recuperacion * self.PESO_PROBABILIDAD * 100
        
        urgency_factor = max(0, (30 - dias_restantes) / 30)
        urgency_score = urgency_factor * self.PESO_URGENCIA * 100
        
        score = value_score + probability_score - urgency_score
        
        score = max(0, min(100, score))
        
        if score >= self.UMBRAL_ALTA:
            prioridad = "urgente"
        elif score >= self.UMBRAL_MEDIA:
            prioridad = "alta"
        else:
            prioridad = "media" if score > 20 else "baja"
        
        valor_ajustado = valor_objetado * probabilidad_recuperacion
        
        return ResultadoScoring(
            score=round(score, 2),
            prioridad=prioridad,
            valor_ajustado=round(valor_ajustado, 2),
            probabilidad_recuperacion=probabilidad_recuperacion,
            dias_hasta_vencimiento=dias_restantes,
            detalles={
                "value_score": round(value_score, 2),
                "probability_score": round(probability_score, 2),
                "urgency_score": round(urgency_score, 2),
                "estado": estado,
            }
        )
    
    def calcular_probabilidad_base(
        self,
        eps: str,
        codigo_glosa: str,
        etapa: str,
    ) -> float:
        """Calcula probabilidad base según historial"""
        
        eps_alta_recuperacion = ["COOSALUD", "FOMAG", "SALUD MIA"]
        eps_baja_recuperacion = ["NUEVA EPS", "POSITIVA", "PPL"]
        
        prob = 0.6
        
        if eps.upper() in eps_alta_recuperacion:
            prob += 0.15
        elif eps.upper() in eps_baja_recuperacion:
            prob -= 0.15
        
        codigos_favorables = ["TA", "SO", "AU", "CO"]
        if any(codigo_glosa.startswith(c) for c in codigos_favorables):
            prob += 0.1
        
        if "RATIF" in etapa.upper():
            prob += 0.1
        
        return max(0.1, min(0.95, prob))