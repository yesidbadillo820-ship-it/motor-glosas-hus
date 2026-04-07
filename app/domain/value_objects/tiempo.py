from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


class Tiempo(str, Enum):
    URGENTE = "urgente"
    NORMAL = "normal"
    TRANQUILO = "tranquilo"


@dataclass(frozen=True)
class Dias:
    valor: int

    @property
    def urgente(self) -> bool:
        return self.valor <= 5

    @property
    def normal(self) -> bool:
        return 5 < self.valor <= 15

    @property
    def tranquilo(self) -> bool:
        return self.valor > 15

    @property
    def vencido(self) -> bool:
        return self.valor < 0

    @property
    def categoria(self) -> Tiempo:
        if self.urgente:
            return Tiempo.URGENTE
        elif self.normal:
            return Tiempo.NORMAL
        return Tiempo.TRANQUILO

    @classmethod
    def desde_fechas(cls, radicacion: date, recepcion: date = None) -> "Dias":
        if recepcion is None:
            recepcion = date.today()
        return cls((recepcion - radicacion).days)