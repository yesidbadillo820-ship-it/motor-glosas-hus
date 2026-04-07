from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class EstadoGlosa(Enum):
    RADICADA = "RADICADA"
    EN_REVISION = "EN_REVISION"
    RESPONDIDA = "RESPONDIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


@dataclass
class GlosaEntity:
    id: Optional[int] = None
    eps: str = ""
    paciente: str = ""
    factura: str = "N/A"
    codigo_glosa: str = "N/A"
    valor_objetado: float = 0.0
    valor_aceptado: float = 0.0
    etapa: str = ""
    estado: EstadoGlosa = EstadoGlosa.RADICADA
    dictamen: str = ""
    dias_restantes: int = 0
    score: int = 0
    modelo_ia: Optional[str] = None
    responsable: Optional[str] = None
    fecha_radicacion: Optional[datetime] = None
    fecha_recepcion: Optional[datetime] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    def puede_transicionar(self, nuevo_estado: EstadoGlosa) -> bool:
        return EstadoGlosa.puede_transicionar(self.estado, nuevo_estado)

    def transicionar(self, nuevo_estado: EstadoGlosa, responsable: str = None) -> bool:
        if self.puede_transicionar(nuevo_estado):
            self.estado = nuevo_estado
            self.actualizado_en = datetime.utcnow()
            if responsable:
                self.responsable = responsable
            return True
        return False

    @staticmethod
    def puede_transicionar(origen: EstadoGlosa, destino: EstadoGlosa) -> bool:
        transiciones = {
            EstadoGlosa.RADICADA: [EstadoGlosa.EN_REVISION],
            EstadoGlosa.EN_REVISION: [EstadoGlosa.RESPONDIDA, EstadoGlosa.CERRADA],
            EstadoGlosa.RESPONDIDA: [EstadoGlosa.ACEPTADA, EstadoGlosa.RECHAZADA],
            EstadoGlosa.ACEPTADA: [EstadoGlosa.CERRADA],
            EstadoGlosa.RECHAZADA: [EstadoGlosa.CERRADA],
            EstadoGlosa.CERRADA: [],
        }
        return destino in transiciones.get(origen, [])