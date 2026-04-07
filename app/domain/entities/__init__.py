from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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


class RolUsuario(str, Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    CARTERA = "cartera"


class GlosaEntity(BaseModel):
    id: Optional[int] = None
    eps: str
    paciente: str
    factura: Optional[str] = "N/A"
    autorizacion: Optional[str] = "N/A"
    codigo_glosa: str
    valor_objetado: float
    valor_aceptado: float
    etapa: str
    estado: EstadoGlosa = EstadoGlosa.RADICADA
    dictamen: Optional[str] = None
    dias_restantes: int = 0
    modelo_ia: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    responsable_id: Optional[int] = None
    score: int = Field(default=0, ge=0, le=100)
    prioridad: Optional[str] = None


class ContratoEntity(BaseModel):
    eps: str
    detalles: str
    version: int = 1
    vigente: bool = True
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None


class UsuarioEntity(BaseModel):
    id: Optional[int] = None
    nombre: str
    email: str
    rol: RolUsuario = RolUsuario.AUDITOR
    eps_permitidos: list[str] = []
    activo: bool = True