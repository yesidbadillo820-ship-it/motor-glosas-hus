from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable
from app.domain.entities import Glosa, EstadoGlosa


class TransicionNoPermitida(Exception):
    pass


@dataclass
class Transicion:
    desde: EstadoGlosa
    hacia: EstadoGlosa
    condicion: Optional[Callable] = None
    accion: Optional[Callable] = None


WORKFLOW_DEFAULT = [
    Transicion(EstadoGlosa.RADICADA, EstadoGlosa.EN_REVISION),
    Transicion(EstadoGlosa.EN_REVISION, EstadoGlosa.RESPONDIDA),
    Transicion(EstadoGlosa.RESPONDIDA, EstadoGlosa.ACEPTADA),
    Transicion(EstadoGlosa.RESPONDIDA, EstadoGlosa.RECHAZADA),
    Transicion(EstadoGlosa.ACEPTADA, EstadoGlosa.CERRADA),
    Transicion(EstadoGlosa.RECHAZADA, EstadoGlosa.CERRADA),
]


class WorkflowEngine:
    def __init__(self, transiciones: list[Transicion] = None):
        self.transiciones = transiciones or WORKFLOW_DEFAULT
        self.sla_horas = {
            EstadoGlosa.RADICADA: 48,
            EstadoGlosa.EN_REVISION: 72,
            EstadoGlosa.RESPONDIDA: 24,
        }
    
    def puede_transicionar(self, estado_actual: str, estado_nuevo: str) -> bool:
        try:
            desde = EstadoGlosa(estado_actual.upper())
            hacia = EstadoGlosa(estado_nuevo.upper())
        except ValueError:
            return False
        
        for t in self.transiciones:
            if t.desde == desde and t.hacia == hacia:
                if t.condicion and not t.condicion(None):
                    return False
                return True
        return False
    
    def transicionar(self, glosa: Glosa, nuevo_estado: str, responsable_id: int = None) -> Glosa:
        if not self.puede_transicionar(glosa.estado, nuevo_estado):
            raise TransicionNoPermitida(
                f"No se puede transicionar de {glosa.estado} a {nuevo_estado}"
            )
        
        glosa.estado = nuevo_estado
        glosa.fecha_estado = datetime.now()
        glosa.responsable_id = responsable_id
        glosa.updated_at = datetime.now()
        
        return glosa
    
    def obtener_sla(self, estado: EstadoGlosa) -> timedelta:
        horas = self.sla_horas.get(estado, 24)
        return timedelta(hours=horas)
    
    def esta_vencido_sla(self, glosa: Glosa) -> bool:
        if not glosa.fecha_estado:
            return True
        
        sla = self.obtener_sla(EstadoGlosa(glosa.estado))
        tiempo_transcurrido = datetime.now() - glosa.fecha_estado
        return tiempo_transcurrido > sla
    
    def obtener_siguiente_estado(self, estado_actual: str) -> Optional[str]:
        try:
            desde = EstadoGlosa(estado_actual.upper())
        except ValueError:
            return None
        
        for t in self.transiciones:
            if t.desde == desde:
                return t.hacia.value
        return None
    
    def obtener_todos_estados(self) -> list[str]:
        return [e.value for e in EstadoGlosa]
