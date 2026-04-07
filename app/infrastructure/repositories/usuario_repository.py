import json
import logging
from typing import Optional, List
from sqlalchemy.orm import Session

from app.infrastructure.db.models import UsuarioRecord

logger = logging.getLogger("usuario_repository")


class UsuarioRepository:
    def __init__(self, db: Session):
        self.db = db

    def crear(
        self,
        nombre: str,
        email: str,
        password_hash: str,
        rol: str = "auditor",
        eps_permitidos: List[str] = None,
    ) -> UsuarioRecord:
        usuario = UsuarioRecord(
            nombre=nombre,
            email=email.lower(),
            password_hash=password_hash,
            rol=rol,
            eps_permitidos=json.dumps(eps_permitidos or []),
            activo=True,
        )
        self.db.add(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        logger.info(f"Usuario creado: {email} - rol: {rol}")
        return usuario

    def obtener_por_email(self, email: str) -> Optional[UsuarioRecord]:
        return self.db.query(UsuarioRecord).filter(UsuarioRecord.email == email.lower()).first()

    def obtener_por_id(self, usuario_id: int) -> Optional[UsuarioRecord]:
        return self.db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()

    def listar_todos(self) -> List[UsuarioRecord]:
        return self.db.query(UsuarioRecord).filter(UsuarioRecord.activo == True).all()

    def actualizar_rol(self, usuario_id: int, rol: str) -> Optional[UsuarioRecord]:
        usuario = self.obtener_por_id(usuario_id)
        if usuario:
            usuario.rol = rol
            self.db.commit()
            self.db.refresh(usuario)
            logger.info(f"Usuario {usuario_id} rol actualizado a {rol}")
        return usuario

    def actualizar_eps_permitidos(self, usuario_id: int, eps_permitidos: List[str]) -> Optional[UsuarioRecord]:
        usuario = self.obtener_por_id(usuario_id)
        if usuario:
            usuario.eps_permitidos = json.dumps(eps_permitidos)
            self.db.commit()
            self.db.refresh(usuario)
        return usuario

    def tiene_acceso_eps(self, usuario: UsuarioRecord, eps: str) -> bool:
        if usuario.rol == "admin":
            return True
        
        eps_permitidos = json.loads(usuario.eps_permitidos) if usuario.eps_permitidos else []
        return eps.upper() in [e.upper() for e in eps_permitidos]

    def desactivar(self, usuario_id: int) -> bool:
        usuario = self.obtener_por_id(usuario_id)
        if usuario:
            usuario.activo = False
            self.db.commit()
            return True
        return False