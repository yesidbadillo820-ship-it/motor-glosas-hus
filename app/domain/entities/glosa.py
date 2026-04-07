from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class Etapa(str, Enum):
    INICIAL = "INICIAL"
    RATIF = "RATIF"
    RATIFICACION = "RATIFICACION"
    RESPUESTA = "RESPUESTA"


class EstadoGlosa(str, Enum):
    RADICADA = "RADICADA"
    EN_REVISION = "EN_REVISION"
    RESPONDIDA = "RESPONDIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


@dataclass
class Glosa:
    id: Optional[int] = None
    eps: str = ""
    paciente: str = ""
    factura: str = "N/A"
    codigo_glosa: str = ""
    valor_objetado: float = 0.0
    valor_aceptado: float = 0.0
    etapa: Etapa = Etapa.INICIAL
    estado: EstadoGlosa = EstadoGlosa.RADICADA
    dictamen: str = ""
    dias_restantes: int = 0
    modelo_ia: Optional[str] = None
    fecha_radicacion: Optional[date] = None
    fecha_recepcion: Optional[date] = None
    creado_en: Optional[datetime] = None
    score: int = 0
    resultado_analisis: Optional[str] = None
    resumen: str = ""

    @property
    def valor_recuperado(self) -> float:
        return self.valor_aceptado

    @property
    def valor_perdido(self) -> float:
        return self.valor_objetado - self.valor_aceptado

    @property
    def esta_vencida(self) -> bool:
        return self.dias_restantes < 0

    @property
    def es_extemporanea(self) -> bool:
        return self.estado == EstadoGlosa.RADICADA and self.dias_restantes < -5

    @property
    def recuperabilidad(self) -> float:
        if self.valor_objetado == 0:
            return 0.0
        return self.valor_aceptado / self.valor_objetado