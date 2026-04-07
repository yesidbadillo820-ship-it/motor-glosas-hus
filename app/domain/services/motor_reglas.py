from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from app.domain.entities.glosa import Glosa, EstadoGlosa


@dataclass
class ResultadoRegla:
    nombre: str
    aplicable: bool
    mensaje: str
    prioridad: int = 0
    icono: str = "⚠"


class Regla(ABC):
    @abstractmethod
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        pass


class ReglaExtemporaneidad(Regla):
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        dias = glosa.dias_restantes
        if dias < -5:
            return ResultadoRegla(
                nombre="Extemporaneidad",
                aplicable=True,
                mensaje="Glosa extemporánea - fuera de término legal",
                prioridad=100,
                icono="⏰"
            )
        elif dias < 0:
            return ResultadoRegla(
                nombre="Vencida",
                aplicable=False,
                mensaje="Glosa vencida - requiere gestión urgente",
                prioridad=90,
                icono="⚠"
            )
        return ResultadoRegla(
            nombre="Término",
            aplicable=False,
            mensaje=f"Días restantes: {dias}",
            prioridad=0,
            icono="✓"
        )


class ReglaCobertura(Regla):
    def __init__(self, contrato_eps: Optional[str] = None):
        self.contrato_eps = contrato_eps

    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        eps = glosa.eps.upper()
        tiene_contrato = self.contrato_eps and eps in self.contrato_eps
        
        if not tiene_contrato:
            return ResultadoRegla(
                nombre="Sin contrato",
                aplicable=True,
                mensaje=f"EPS {eps} sin contrato definido - aplicar tarifa SOAT pleno",
                prioridad=50,
                icono="📋"
            )
        return ResultadoRegla(
            nombre="Contrato",
            aplicable=False,
            mensaje=f"EPS {eps} con contrato activo",
            prioridad=0,
            icono="✓"
        )


class ReglaValor(Regla):
    def evaluar(self, glosa: Glosa) -> ResultadoRegla:
        valor = glosa.valor_objetado
        if valor >= 5_000_000:
            return ResultadoRegla(
                nombre="Alto valor",
                aplicable=True,
                mensaje=f"Glosa de alto valor: ${valor:,.0f}",
                prioridad=80,
                icono="💰"
            )
        elif valor >= 1_000_000:
            return ResultadoRegla(
                nombre="Valor medio",
                aplicable=True,
                mensaje=f"Glosa valor significativo",
                prioridad=40,
                icono="💵"
            )
        return ResultadoRegla(
            nombre="Bajo valor",
            aplicable=False,
            mensaje=f"Glosa de bajo valor",
            prioridad=10,
            icono="💲"
        )


class MotorReglas:
    def __init__(self, reglas: List[Regla]):
        self.reglas = reglas

    def evaluar(self, glosa: Glosa) -> List[ResultadoRegla]:
        resultados = []
        for regla in self.reglas:
            resultado = regla.evaluar(glosa)
            if resultado.aplicable:
                resultados.append(resultado)
        
        resultados.sort(key=lambda r: r.prioridad, reverse=True)
        return resultados

    def adicionar_regla(self, regla: Regla):
        self.reglas.append(regla)


MOTOR_DEFAULT = MotorReglas([
    ReglaExtemporaneidad(),
    ReglaValor(),
    ReglaCobertura(),
])