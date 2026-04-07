from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
from app.domain.entities import Glosa, ResultadoRegla


class ReglaBase(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        pass
    
    @property
    @abstractmethod
    def nombre(self) -> str:
        pass
    
    @abstractmethod
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        pass


class ReglaExtemporaneidad(ReglaBase):
    @property
    def id(self) -> str:
        return "RE001"
    
    @property
    def nombre(self) -> str:
        return "Extemporaneidad"
    
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        if glosa.dias_habiles == 0:
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=True,
                mensaje="Sin información de fechas",
                severidad="baja"
            )
        
        if glosa.dias_habiles > 20:
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=False,
                mensaje=f"GLOSA EXTEMPORÁNEA: {glosa.dias_habiles} días hábiles (límite: 20 días)",
                severidad="critica"
            )
        
        return ResultadoRegla(
            regla_id=self.id,
            nombre=self.nombre,
            cumple=True,
            mensaje=f"DENTRO DE TÉRMINOS: {glosa.dias_habiles} días hábiles",
            severidad="baja"
        )


class ReglaContrato(ReglaBase):
    def __init__(self, contratos_db: dict):
        self.contratos = contratos_db
    
    @property
    def id(self) -> str:
        return "RE002"
    
    @property
    def nombre(self) -> str:
        return "Vigencia Contractual"
    
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        eps_key = glosa.eps.upper().strip()
        contrato = self.contratos.get(eps_key)
        
        if not contrato or "SIN CONTRATO" in contrato.upper():
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=False,
                mensaje="SIN CONTRATO VIGENTE - Aplica tarifa SOAT plena",
                severidad="media"
            )
        
        return ResultadoRegla(
            regla_id=self.id,
            nombre=self.nombre,
            cumple=True,
            mensaje=f"Contrato vigente: {eps_key}",
            severidad="baja"
        )


class ReglaCobertura(ReglaBase):
    def __init__(self, eps_excluyentes: list[str] = None):
        self.eps_excluyentes = eps_excluyentes or [
            "PRECIMED", "SALUD MIA", "FAMISANAR"
        ]
    
    @property
    def id(self) -> str:
        return "RE003"
    
    @property
    def nombre(self) -> str:
        return "Cobertura EPS"
    
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        eps = glosa.eps.upper()
        
        if eps in self.eps_excluyentes:
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=False,
                mensaje=f"EPS {eps} con exclusiones conocidas - Revisar manualmente",
                severidad="media"
            )
        
        return ResultadoRegla(
            regla_id=self.id,
            nombre=self.nombre,
            cumple=True,
            mensaje=f"EPS {eps} sin exclusiones críticas",
            severidad="baja"
        )


class ReglaValorMinimo(ReglaBase):
    def __init__(self, umbral: float = 50000):
        self.umbral = umbral
    
    @property
    def id(self) -> str:
        return "RE004"
    
    @property
    def nombre(self) -> str:
        return "Valor Mínimo"
    
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        if glosa.valor_objetado < self.umbral:
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=True,
                mensaje=f"Valor bajo umbral (${self.umbral:,.0f}) - Revisión opcional",
                severidad="baja"
            )
        
        return ResultadoRegla(
            regla_id=self.id,
            nombre=self.nombre,
            mensaje=f"Valor obj: ${glosa.valor_objetado:,.0f} - REQUIERE ATENCIÓN",
            cumple=True,
            severidad="media"
        )


class ReglaUrgencia(ReglaBase):
    def __init__(self, dias_alerta: int = 5):
        self.dias_alerta = dias_alerta
    
    @property
    def id(self) -> str:
        return "RE005"
    
    @property
    def nombre(self) -> str:
        return "Urgencia de Tiempo"
    
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        if glosa.dias_restantes <= 0:
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=False,
                mensaje="VENCIDA - Sin días restantes",
                severidad="critica"
            )
        
        if glosa.dias_restantes <= self.dias_alerta:
            return ResultadoRegla(
                regla_id=self.id,
                nombre=self.nombre,
                cumple=False,
                mensaje=f"PRÓXIMA A VENCER: {glosa.dias_restantes} días restantes",
                severidad="alta"
            )
        
        return ResultadoRegla(
            regla_id=self.id,
            nombre=self.nombre,
            cumple=True,
            mensaje=f"Tiempo disponible: {glosa.dias_restantes} días",
            severidad="baja"
        )


class MotorReglas:
    def __init__(self, reglas: list[ReglaBase]):
        self.reglas = reglas
    
    def evaluar(self, glosa: Glosa) -> list[ResultadoRegla]:
        resultados = []
        for regla in self.reglas:
            try:
                resultado = regla.evaluar(glosa)
                resultados.append(resultado)
            except Exception as e:
                resultados.append(ResultadoRegla(
                    regla_id=regla.id,
                    nombre=regla.nombre,
                    cumple=False,
                    mensaje=f"Error evaluando regla: {str(e)}",
                    severidad="media"
                ))
        return resultados
    
    def tiene_fallas_criticas(self, resultados: list[ResultadoRegla]) -> bool:
        return any(r.severidad == "critica" and not r.cumple for r in resultados)
