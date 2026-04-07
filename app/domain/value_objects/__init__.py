from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class ResultadoRegla(BaseModel):
    aplico: bool
    codigo: str
    descripcion: str
    gravedad: str = "baja"
    mensaje: str = ""


class ScoringInput(BaseModel):
    valor_objetado: float
    valor_aceptado: float
    dias_restantes: int
    dias_vencidos: int = 0
    probabilidad_recuperacion: float = 0.5
    es_extemporanea: bool = False
    es_ratificacion: bool = False
    eps: str = ""


class ScoringOutput(BaseModel):
    score_total: int = Field(ge=0, le=100)
    prioridad: str
    valor_recuperable: float
    sugerencia_accion: str


class InfoTemporal(BaseModel):
    dias_habiles: int
    es_extemporanea: bool
    dias_restantes: int
    esta_vencida: bool
    mensaje_estado: str
    color_estado: str


class WorkflowTransition(BaseModel):
    desde: str
    hacia: str
    valida: bool = True
    mensaje: str = ""