from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from enum import Enum


class TipoGlosa(str, Enum):
    GLOSA = "GLOSA"
    DEVOLUCION = "DEVOLUCION"


class CodigoRespuesta(str, Enum):
    RE9502 = "RE9502"
    RE9901 = "RE9901"
    RE9601 = "RE9601"
    RE9602 = "RE9602"


class TipoEstrategia(str, Enum):
    TARIFA = "TA"
    SOPORTES = "SO"
    AUTORIZACION = "AU"
    COBERTURA = "CO"
    PERTINENCIA = "PE"
    FACTURACION = "FA"
    INDETERMINADA = "SE"


@dataclass
class ValorMonetario:
    cantidad: float
    moneda: str = "COP"
    
    def __str__(self) -> str:
        return f"$ {self.cantidad:,.2f}"
    
    def __add__(self, other: "ValorMonetario") -> "ValorMonetario":
        return ValorMonetario(self.cantidad + other.cantidad, self.moneda)


@dataclass
class RangoFechas:
    fecha_inicio: date
    fecha_fin: date
    
    @property
    def dias(self) -> int:
        return (self.fecha_fin - self.fecha_inicio).days


@dataclass
class ResultadoRegla:
    nombre: str
    cumple: bool
    mensaje: str
    severidad: str = "info"


@dataclass
class ResultadoScoring:
    score: float
    prioridad: str
    valor_ajustado: float
    probabilidad_recuperacion: float
    dias_hasta_vencimiento: int
    detalles: dict