from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class EstadoGlosa(str, Enum):
    RADICADA = "RADICADA"
    EN_REVISION = "EN_REVISION"
    RESPONDIDA = "RESPONDIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


class RolUsuario(str, Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    CARTERA = "cartera"


class PrioridadGlosa(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"


@dataclass
class Glosa:
    id: Optional[int]
    eps: str
    paciente: str
    factura: str
    codigo_glosa: str
    valor_objetado: float
    valor_aceptado: float
    etapa: str
    estado: EstadoGlosa
    dictamen: str
    dias_restantes: int
    modelo_ia: Optional[str]
    score: int
    prioridad: PrioridadGlosa
    created_at: datetime
    updated_at: datetime
    responsable_id: Optional[int] = None
    
    @property
    def valor_recuperado(self) -> float:
        return self.valor_objetado - self.valor_aceptado


@dataclass
class Contrato:
    eps: str
    version: int
    detalles: str
    fecha_inicio: datetime
    fecha_fin: Optional[datetime]
    activo: bool = True


@dataclass
class Usuario:
    id: int
    nombre: str
    email: str
    rol: RolUsuario
    eps_asignadas: list[str]
    activo: bool = True