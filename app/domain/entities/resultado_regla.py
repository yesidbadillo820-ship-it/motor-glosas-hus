from dataclasses import dataclass
from typing import Any


@dataclass
class ResultadoRegla:
    nombre: str
    aplico: bool
    resultado: Any
    mensaje: str
    prioridad: int = 0

    def __bool__(self) -> bool:
        return self.aplico