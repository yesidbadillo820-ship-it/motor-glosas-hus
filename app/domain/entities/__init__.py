from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class EstadoGlosa(str, Enum):
    RADICADA = "RADICADA"
    EN_REVISION = "EN_REVISION"
    RESPONDIDA = "RESPONDIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


class EtapaGlosa(str, Enum):
    INICIAL = "INICIAL"
    RATIF = "RATIF"
    RATIFICACION = "RATIFICACION"
    RESPUESTA = "RESPUESTA"


@dataclass
class Glosa:
    id: Optional[int] = None
    eps: str = ""
    paciente: str = ""
    codigo_glosa: str = "N/A"
    valor_objetado: float = 0.0
    valor_aceptado: float = 0.0
    etapa: str = "INICIAL"
    estado: str = "RADICADA"
    dictamen: str = ""
    dias_restantes: int = 0
    dias_habiles: int = 0
    es_extemporanea: bool = False
    score: int = 0
    modelo_ia: Optional[str] = None
    responsable_id: Optional[int] = None
    fecha_radicacion: Optional[datetime] = None
    fecha_recepcion: Optional[datetime] = None
    fecha_estado: Optional[datetime] = None
    observaciones: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Contrato:
    eps: str
    detalles: str
    version: int = 1
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    activo: bool = True


@dataclass
class Usuario:
    id: int
    nombre: str
    email: str
    rol: str = "auditor"
    eps_asignadas: list[str] = None
    
    def __post_init__(self):
        if self.eps_asignadas is None:
            self.eps_asignadas = []


@dataclass
class Regla:
    id: str
    nombre: str
    descripcion: str
    tipo: str
    activa: bool = True
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None


@dataclass
class ResultadoRegla:
    regla_id: str
    nombre: str
    cumple: bool
    mensaje: str
    severidad: str = "media"
