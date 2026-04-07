from typing import Protocol
from app.domain.value_objects import ResultadoRegla


class ReglaGlosa(Protocol):
    """Protocolo para reglas de glosas - permite extensibilidad"""
    
    def evaluar(self, glosa_data: dict) -> ResultadoRegla:
        """Evalúa la glosa contra esta regla"""
        ...
    
    @property
    def nombre(self) -> str:
        """Nombre identificador de la regla"""
        ...
    
    @property
    def descripcion(self) -> str:
        """Descripción para documentation"""
        ...


class MotorReglas:
    """Motor de evaluación de reglas para glosas"""
    
    def __init__(self):
        self._reglas: list[ReglaGlosa] = []
    
    def agregar_regla(self, regla: ReglaGlosa) -> "MotorReglas":
        """Agrega una regla al motor"""
        self._reglas.append(regla)
        return self
    
    def agregar_reglas(self, reglas: list[ReglaGlosa]) -> "MotorReglas":
        """Agrega múltiples reglas al motor"""
        self._reglas.extend(reglas)
        return self
    
    def evaluar_todas(self, glosa_data: dict) -> list[ResultadoRegla]:
        """Evalúa todas las reglas registradas"""
        return [regla.evaluar(glosa_data) for regla in self._reglas]
    
    def evaluar_y_ Filtrar(self, glosa_data: dict, severidades: list[str] = None) -> list[ResultadoRegla]:
        """Evalúa y filtra por severidades"""
        resultados = self.evaluar_todas(glosa_data)
        if severidades:
            return [r for r in resultados if r.severidad in severidades]
        return resultados
    
    def tiene_infracciones_criticas(self, glosa_data: dict) -> bool:
        """Verifica si hay infracciones críticas que requieren acción inmediata"""
        resultados = self.evaluar_todas(glosa_data)
        return any(r.severidad == "critica" and not r.cumple for r in resultados)