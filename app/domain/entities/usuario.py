from dataclasses import dataclass
from typing import Optional
from enum import Enum


class Rol(str, Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    CARTERA = "cartera"


@dataclass
class Usuario:
    id: Optional[int] = None
    nombre: str = ""
    email: str = ""
    password_hash: str = ""
    rol: Rol = Rol.AUDITOR

    def puede_editar(self) -> bool:
        return self.rol in [Rol.ADMIN, Rol.AUDITOR]

    def puede_ver_financiero(self) -> bool:
        return self.rol in [Rol.ADMIN, Rol.CARTERA]

    def puede_admin(self) -> bool:
        return self.rol == Rol.ADMIN