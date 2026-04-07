from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TipoDocumento(str, Enum):
    FACTURA = "factura"
    AUTORIZACION = "autorizacion"
    CONTRATO = "contrato"
    SOPORTE = "soporte"


@dataclass(frozen=True)
class Documento:
    tipo: TipoDocumento
    numero: str
    url: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.tipo.value}: {self.numero}"