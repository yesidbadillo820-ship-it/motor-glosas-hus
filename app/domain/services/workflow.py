from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
from app.domain.entities.glosa import Glosa, EstadoGlosa, Etapa


class Estado(str, Enum):
    RADICADA = "RADICADA"
    EN_REVISION = "EN_REVISION"
    RESPONDIDA = "RESPONDIDA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"
    CERRADA = "CERRADA"


@dataclass
class Transicion:
    desde: Estado
    hacia: Estado
    accion: str
    requiere_usuario: bool = True
    sla_dias: Optional[int] = None


@dataclass
class ValidacionTransicion:
    valida: bool
    mensaje: str
    puede_forzar: bool = False


WORKFLOW_DEFAULT = {
    Estado.RADICADA: [
        Transicion(Estado.RADICADA, Estado.EN_REVISION, "Iniciar revisión", True, 5),
    ],
    Estado.EN_REVISION: [
        Transicion(Estado.EN_REVISION, Estado.RESPONDIDA, "Responder glosa", True, 10),
        Transicion(Estado.EN_REVISION, Estado.CERRADA, "Cerrar sin respuesta", True, None),
    ],
    Estado.RESPONDIDA: [
        Transicion(Estado.RESPONDIDA, Estado.ACEPTADA, "Aceptada por EPS", False, 15),
        Transicion(Estado.RESPONDIDA, Estado.RECHAZADA, "Rechazada por EPS", False, None),
    ],
    Estado.ACEPTADA: [
        Transicion(Estado.ACEPTADA, Estado.CERRADA, "Cerrar glosa", True, None),
    ],
    Estado.RECHAZADA: [
        Transicion(Estado.RECHAZADA, Estado.CERRADA, "Cerrar glosa", True, None),
    ],
    Estado.CERRADA: [],
}


class WorkflowService:
    def __init__(self, workflow: Optional[dict] = None):
        self.workflow = workflow or WORKFLOW_DEFAULT

    def obtener_transiciones(self, estado_actual: Estado) -> List[Transicion]:
        return self.workflow.get(estado_actual, [])

    def puede_transicionar(self, desde: Estado, hacia: Estado) -> ValidacionTransicion:
        transiciones = self.obtener_transiciones(desde)
        
        for transicion in transiciones:
            if transicion.hacia == hacia:
                return ValidacionTransicion(
                    valida=True,
                    mensaje=f"Transición permitida: {transicion.accion}"
                )
        
        return ValidacionTransicion(
            valida=False,
            mensaje=f"No hay transición de {desde.value} a {hacia.value}"
        )

    def obtener_sla(self, desde: Estado, hacia: Estado) -> Optional[int]:
        transiciones = self.obtener_transiciones(desde)
        for transicion in transiciones:
            if transicion.hacia == hacia:
                return transicion.sla_dias
        return None


WORKFLOW_SERVICE_DEFAULT = WorkflowService()