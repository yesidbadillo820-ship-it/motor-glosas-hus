from dataclasses import dataclass
from typing import Optional


@dataclass
class Contrato:
    eps: str = ""
    detalles: str = ""
    tarifa_soat: Optional[str] = None
    tarifa_institucional: Optional[str] = None
    incluye_oncologicos: bool = False
    incluye_maos: bool = False
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    version: int = 1

    @property
    def activo(self) -> bool:
        return bool(self.eps and self.detalles)

    def tiene_cobertura(self, servicio: str) -> bool:
        servicios_maos = ["MAOS", "oncologicos"]
        if servicio in servicios_maos:
            if servicio == "MAOS":
                return self.incluye_maos
            if servicio == "oncologicos":
                return self.incluye_oncologicos
        return True