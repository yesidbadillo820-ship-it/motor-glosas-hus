from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class ValorMonetario:
    valor: float
    moneda: str = "COP"
    
    def __str__(self):
        return f"${self.valor:,.2f} {self.moneda}"
    
    def a_float(self) -> float:
        return self.valor


@dataclass(frozen=True)
class Periodo:
    fecha_inicio: datetime
    fecha_fin: datetime
    
    def dias(self) -> int:
        return (self.fecha_fin - self.fecha_inicio).days
    
    def contains(self, fecha: datetime) -> bool:
        return self.fecha_inicio <= fecha <= self.fecha_fin


@dataclass(frozen=True)
class CodigoRespuesta:
    codigo: str
    descripcion: str
    
    def __str__(self):
        return f"{self.codigo}: {self.descripcion}"


@dataclass(frozen=True)
class ScoringGlosa:
    score: int
    prioridad: str
    valor_recuperable_estimado: float
    probabilidad_recuperacion: float
    
    @property
    def categoria(self) -> str:
        if self.score >= 80:
            return "critica"
        elif self.score >= 60:
            return "alta"
        elif self.score >= 40:
            return "media"
        return "baja"
