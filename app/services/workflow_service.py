"""
Servicio de workflow para glosas médicas.
Implementa state machine: RADICADA → RESPONDIDA → RATIFICADA → CONCILIADA/LEVANTADA/ESCALADA_SNS
"""
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass

from app.core.logging_utils import logger


class EstadoGlosa(str, Enum):
    RADICADA = "RADICADA"
    RESPONDIDA = "RESPONDIDA"
    RATIFICADA = "RATIFICADA"
    CONCILIADA = "CONCILIADA"
    LEVANTADA = "LEVANTADA"
    ESCALADA_SNS = "ESCALADA_SNS"
    ACEPTADA = "ACEPTADA"
    PARCIALMENTE_ACEPTADA = "PARCIALMENTE_ACEPTADA"


@dataclass
class TransicionWorkflow:
    desde: str
    hacia: str
    accion: str
    requiere_nota: bool = False


TRANSICIONES_PERMITIDAS = [
    TransicionWorkflow("RADICADA", "RESPONDIDA", "Responder glosa"),
    TransicionWorkflow("RESPONDIDA", "RATIFICADA", "EPS ratifica glosa"),
    TransicionWorkflow("RESPONDIDA", "LEVANTADA", "EPS retira glosa"),
    TransicionWorkflow("RESPONDIDA", "CONCILIADA", "Conciliación exitosa"),
    TransicionWorkflow("RATIFICADA", "CONCILIADA", "Conciliación exitosa"),
    TransicionWorkflow("RATIFICADA", "LEVANTADA", "EPS retira glosa"),
    TransicionWorkflow("RATIFICADA", "ESCALADA_SNS", "Escalar a Superintendencia"),
    TransicionWorkflow("CONCILIADA", "LEVANTADA", "Confirmar levantamiento"),
]


class WorkflowService:
    """Gestiona transiciones de estado de glosas."""
    
    @staticmethod
    def obtener_transiciones_validas(estado_actual: str) -> List[TransicionWorkflow]:
        """Retorna las transiciones válidas desde el estado actual."""
        return [
            t for t in TRANSICIONES_PERMITIDAS
            if t.desde == estado_actual
        ]
    
    @staticmethod
    def puede_transicionar(desde: str, hacia: str) -> bool:
        """Verifica si una transición es válida."""
        return any(
            t.desde == desde and t.hacia == hacia
            for t in TRANSICIONES_PERMITIDAS
        )
    
    @staticmethod
    def transicionar(
        glosa,
        nuevo_estado: str,
        db=None,
        nota: Optional[str] = None,
        responsable: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Ejecuta una transición de estado.
        
        Returns:
            tuple: (exito: bool, mensaje: str)
        """
        estado_actual = getattr(glosa, "workflow_state", None) or getattr(glosa, "estado", "RADICADA")
        
        if not WorkflowService.puede_transicionar(estado_actual, nuevo_estado):
            transiciones = WorkflowService.obtener_transiciones_validas(estado_actual)
            disponibles = [t.hacia for t in transiciones]
            return False, (
                f"No se puede cambiar de {estado_actual} a {nuevo_estado}. "
                f"Estados disponibles: {disponibles}"
            )
        
        try:
            glosa.workflow_state = nuevo_estado
            glosa.estado = nuevo_estado
            
            if nota:
                glosa.nota_workflow = nota[:500] if hasattr(glosa, "nota_workflow") else None
            
            if responsable and hasattr(glosa, "responsable"):
                glosa.responsable = responsable
            
            if db:
                db.commit()
                db.refresh(glosa)
            
            logger.info(f"Workflow: {estado_actual} → {nuevo_estado} | glosa_id={getattr(glosa, 'id', 'N/A')}")
            
            return True, f"Glosa actualizada a {nuevo_estado}"
            
        except Exception as e:
            if db:
                db.rollback()
            logger.error(f"Workflow error: {e}")
            return False, f"Error al actualizar estado: {str(e)}"
    
    @staticmethod
    def es_terminal(estado: str) -> bool:
        """Indica si el estado es terminal (no hay más transiciones)."""
        return estado in ["LEVANTADA", "CONCILIADA", "ESCALADA_SNS"]
    
    @staticmethod
    def requiere_accion(estado: str) -> dict:
        """Retorna información sobre acciones requeridas según estado."""
        acciones = {
            "RADICADA": {
                "mensaje": "Glosa recibida - pendiente de análisis",
                "urgencia": "alta",
                "siguiente": ["RESPONDIDA"]
            },
            "RESPONDIDA": {
                "mensaje": "Respuesta enviada - esperando decisión EPS",
                "urgencia": "media",
                "siguiente": ["RATIFICADA", "LEVANTADA", "CONCILIADA"]
            },
            "RATIFICADA": {
                "mensaje": "EPS ratifica glosa - requiere conciliación o escalamiento",
                "urgencia": "alta",
                "siguiente": ["CONCILIADA", "LEVANTADA", "ESCALADA_SNS"]
            },
            "CONCILIADA": {
                "mensaje": "En conciliación - programar audiencia",
                "urgencia": "alta",
                "siguiente": ["LEVANTADA"]
            },
            "LEVANTADA": {
                "mensaje": "Glosa levantada - caso cerrado",
                "urgencia": "baja",
                "siguiente": []
            },
            "ESCALADA_SNS": {
                "mensaje": "Escalado a Superintendencia Nacional de Salud",
                "urgencia": "alta",
                "siguiente": []
            },
        }
        return acciones.get(estado, {"mensaje": "Estado desconocido", "urgencia": "baja", "siguiente": []})
