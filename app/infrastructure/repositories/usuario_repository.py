from typing import List, Optional
from app.domain.entities.usuario import Usuario, Rol
from app.database import SessionLocal
from app.models.db import UsuarioRecord
from app.auth import get_password_hash, verify_password


class UsuarioRepository:
    def guardar(self, usuario: Usuario) -> int:
        db = SessionLocal()
        try:
            record = UsuarioRecord(
                nombre=usuario.nombre,
                email=usuario.email.lower(),
                password_hash=usuario.password_hash,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record.id
        finally:
            db.close()

    def buscar_por_id(self, usuario_id: int) -> Optional[Usuario]:
        db = SessionLocal()
        try:
            record = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
            if not record:
                return None
            return self._to_entity(record)
        finally:
            db.close()

    def buscar_por_email(self, email: str) -> Optional[Usuario]:
        db = SessionLocal()
        try:
            record = db.query(UsuarioRecord).filter(UsuarioRecord.email == email.lower()).first()
            if not record:
                return None
            return self._to_entity(record)
        finally:
            db.close()

    def autenticar(self, email: str, password: str) -> Optional[Usuario]:
        usuario = self.buscar_por_email(email)
        if not usuario:
            return None
        if verify_password(password, usuario.password_hash):
            return usuario
        return None

    def listar_todos(self) -> List[Usuario]:
        db = SessionLocal()
        try:
            records = db.query(UsuarioRecord).all()
            return [self._to_entity(r) for r in records]
        finally:
            db.close()

    def actualizar(self, usuario_id: int, datos: dict) -> bool:
        db = SessionLocal()
        try:
            db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).update(datos)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def eliminar(self, usuario_id: int) -> bool:
        db = SessionLocal()
        try:
            record = db.query(UsuarioRecord).filter(UsuarioRecord.id == usuario_id).first()
            if record:
                db.delete(record)
                db.commit()
                return True
            return False
        finally:
            db.close()

    def _to_entity(self, record: UsuarioRecord) -> Usuario:
        return Usuario(
            id=record.id,
            nombre=record.nombre,
            email=record.email,
            password_hash=record.password_hash,
            rol=Rol.AUDITOR,
        )