from datetime import datetime
from typing import Optional
from enum import Enum
from dataclasses import dataclass, field


class EstadoWorkflow(str, Enum):
    RADICADA = "RADICADA"
    EN_REVISION = "EN_REVISION"
    RESPONDIDA = "RESPONDIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


TRANSICIONES_VALIDAS = {
    EstadoWorkflow.RADICADA: [EstadoWorkflow.EN_REVISION, EstadoWorkflow.CERRADA],
    EstadoWorkflow.EN_REVISION: [EstadoWorkflow.RESPONDIDA, EstadoWorkflow.RADICADA],
    EstadoWorkflow.RESPONDIDA: [EstadoWorkflow.ACEPTADA, EstadoWorkflow.RECHAZADA, EstadoWorkflow.EN_REVISION],
    EstadoWorkflow.ACEPTADA: [EstadoWorkflow.CERRADA],
    EstadoWorkflow.RECHAZADA: [EstadoWorkflow.CERRADA],
    EstadoWorkflow.CERRADA: [],
}


@dataclass
class TransicionWorkflow:
    desde: EstadoWorkflow
    hacia: EstadoWorkflow
    usuario_id: int
    motivo: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowState:
    glosa_id: int
    estado_actual: EstadoWorkflow
    responsable_id: Optional[int] = None
    fecha_cambio: datetime = field(default_factory=datetime.now)
    historial: list[TransicionWorkflow] = field(default_factory=list)
    sla_inicio: Optional[datetime] = None
    sla_fin: Optional[datetime] = None


class WorkflowEngine:
    """
    Motor de workflow para glosas.
    
    Maneja estados, transiciones, responsables y SLAs.
    """
    
    DIAS_SLA = {
        EstadoWorkflow.RADICADA: 2,
        EstadoWorkflow.EN_REVISION: 10,
        EstadoWorkflow.RESPONDIDA: 15,
    }
    
    def __init__(self):
        pass
    
    def es_transicion_valida(
        self,
        desde: EstadoWorkflow,
        hacia: EstadoWorkflow,
    ) -> bool:
        """Valida si una transición es permitida"""
        return hacia in TRANSICIONES_VALIDAS.get(desde, [])
    
    def obtener_siguiente_estados(self, estado_actual: EstadoWorkflow) -> list[EstadoWorkflow]:
        """Retorna los estados válidos siguientes"""
        return TRANSICIONES_VALIDAS.get(estado_actual, [])
    
    def crear_transicion(
        self,
        desde: EstadoWorkflow,
        hacia: EstadoWorkflow,
        usuario_id: int,
        motivo: Optional[str] = None,
    ) -> Optional[TransicionWorkflow]:
        """Crea una transición si es válida"""
        if not self.es_transicion_valida(desde, hacia):
            return None
        
        return TransicionWorkflow(
            desde=desde,
            hacia=hacia,
            usuario_id=usuario_id,
            motivo=motivo,
            timestamp=datetime.now(),
        )
    
    def calcular_sla(
        self,
        estado: EstadoWorkflow,
        fecha_inicio: datetime,
    ) -> datetime:
        """Calcula fecha límite SLA para un estado"""
        dias = self.DIAS_SLA.get(estado, 0)
        return fecha_inicio + timedelta(days=dias)
    
    def esta_vencido(
        self,
        sla_fin: Optional[datetime],
    ) -> bool:
        """Verifica si el SLA está vencido"""
        if not sla_fin:
            return False
        return datetime.now() > sla_fin
    
    def obtener_tiempo_restante(
        self,
        sla_fin: Optional[datetime],
    ) -> Optional[int]:
        """Días restantes antes del vencimiento del SLA"""
        if not sla_fin:
            return None
        diff = sla_fin - datetime.now()
        return max(0, diff.days)


from datetime import timedelta