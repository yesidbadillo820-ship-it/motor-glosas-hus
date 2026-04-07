from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Any, Optional
from datetime import datetime, timedelta
import re

from app.domain.entities.glosa import GlosaEntity
from app.domain.entities.resultado_regla import ResultadoRegla


class Regla(ABC):
    @abstractmethod
    def evaluar(self, glosa: GlosaEntity, contexto: dict = None) -> ResultadoRegla:
        pass

    @property
    @abstractmethod
    def nombre(self) -> str:
        pass

    @property
    def prioridad(self) -> int:
        return 0


class ReglaExtemporaneidad(Regla):
    DIAS_LIMITE = 20

    @property
    def nombre(self) -> str:
        return "Extemporaneidad"

    @property
    def prioridad(self) -> int:
        return 100

    def evaluar(self, glosa: GlosaEntity, contexto: dict = None) -> ResultadoRegla:
        dias = getattr(glosa, "dias_restantes", 0)
        es_extemporanea = dias < 0 or dias > self.DIAS_LIMITE
        
        return ResultadoRegla(
            nombre=self.nombre,
            aplico=True,
            resultado={"es_extemporanea": es_extemporanea, "dias": dias},
            mensaje=f"GIRO {'EXTEMPORÁNEA' if es_extemporanea else 'DENTRO DE TÉRMINOS'} ({dias} días)",
            prioridad=self.prioridad
        )


class ReglaCobertura(Regla):
    @property
    def nombre(self) -> str:
        return "CoberturaEPS"

    @property
    def prioridad(self) -> int:
        return 80

    def evaluar(self, glosa: GlosaEntity, contexto: dict = None) -> ResultadoRegla:
        eps = getattr(glosa, "eps", "").upper()
        contratos = contexto.get("contratos", {}) if contexto else {}
        info_contrato = contratos.get(eps, "")
        
        tiene_contrato = bool(info_contrato and "SIN CONTRATO" not in info_contrato.upper())
        
        return ResultadoRegla(
            nombre=self.nombre,
            aplico=True,
            resultado={"tiene_contrato": tiene_contrato, "eps": eps},
            mensaje=f"EPS: {eps} - {'CONTRATO ACTIVO' if tiene_contrato else 'SIN CONTRATO'}",
            prioridad=self.prioridad
        )


class ReglaContrato(Regla):
    @property
    def nombre(self) -> str:
        return "ReglaContrato"

    @property
    def prioridad(self) -> int:
        return 70

    def evaluar(self, glosa: GlosaEntity, contexto: dict = None) -> ResultadoRegla:
        eps = getattr(glosa, "eps", "").upper()
        contratos = contexto.get("contratos", {}) if contexto else {}
        info_contrato = contratos.get(eps, "SIN CONTRATO PACTADO")
        
        return ResultadoRegla(
            nombre=self.nombre,
            aplico=True,
            resultado={"contrato": info_contrato},
            mensaje=f"Contrato: {info_contrato[:50]}..." if len(info_contrato) > 50 else f"Contrato: {info_contrato}",
            prioridad=self.prioridad
        )


class ReglaValor(Regla):
    @property
    def nombre(self) -> str:
        return "ReglaValor"

    @property
    def prioridad(self) -> int:
        return 60

    def evaluar(self, glosa: GlosaEntity, contexto: dict = None) -> ResultadoRegla:
        valor = getattr(glosa, "valor_objetado", 0.0)
        
        if valor > 10000000:
            nivel = "ALTO"
        elif valor > 1000000:
            nivel = "MEDIO"
        else:
            nivel = "BAJO"
        
        return ResultadoRegla(
            nombre=self.nombre,
            aplico=True,
            resultado={"valor": valor, "nivel": nivel},
            mensaje=f"Valor: ${valor:,.0f} ({nivel})",
            prioridad=self.prioridad
        )


class MotorReglas:
    def __init__(self, reglas: List[Regla] = None):
        self.reglas: List[Regla] = reglas or [
            ReglaExtemporaneidad(),
            ReglaCobertura(),
            ReglaContrato(),
            ReglaValor(),
        ]
    
    def agregar_regla(self, regla: Regla) -> "MotorReglas":
        self.reglas.append(regla)
        return self
    
    def evaluar(self, glosa: GlosaEntity, contexto: dict = None) -> List[ResultadoRegla]:
        resultados = []
        for regla in sorted(self.reglas, key=lambda r: r.prioridad, reverse=True):
            try:
                resultado = regla.evaluar(glosa, contexto)
                resultados.append(resultado)
            except Exception as e:
                resultados.append(ResultadoRegla(
                    nombre=regla.nombre,
                    aplico=False,
                    resultado=None,
                    mensaje=f"Error: {str(e)}",
                    prioridad=regla.prioridad
                ))
        return resultados
    
    def evaluar_todos(self, glosas: List[GlosaEntity], contexto: dict = None) -> List[List[ResultadoRegla]]:
        return [self.evaluar(g, contexto) for g in glosas]