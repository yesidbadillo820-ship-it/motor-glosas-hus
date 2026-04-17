"""Hilo de comentarios por glosa (colaboración entre el equipo)."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.db import ComentarioGlosaRecord, GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/glosas/{glosa_id}/comentarios", tags=["comentarios"])


class ComentarioInput(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)
    mencion: Optional[str] = None  # email mencionado


@router.get("/")
def listar(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista todos los comentarios de una glosa en orden cronológico."""
    if not db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first():
        raise HTTPException(404, "Glosa no encontrada")
    comentarios = (
        db.query(ComentarioGlosaRecord)
        .filter(ComentarioGlosaRecord.glosa_id == glosa_id)
        .order_by(ComentarioGlosaRecord.creado_en.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "autor_email": c.autor_email,
            "autor_nombre": c.autor_nombre,
            "autor_rol": c.autor_rol,
            "texto": c.texto,
            "mencion": c.mencion,
            "resuelto": bool(c.resuelto),
            "resuelto_por": c.resuelto_por,
            "resuelto_en": c.resuelto_en.isoformat() if c.resuelto_en else None,
            "creado_en": c.creado_en.isoformat() if c.creado_en else None,
        }
        for c in comentarios
    ]


@router.post("/", status_code=201)
def agregar(
    glosa_id: int,
    data: ComentarioInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Agrega un comentario al hilo. Detecta menciones @email automáticamente."""
    if not db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first():
        raise HTTPException(404, "Glosa no encontrada")

    # Detectar mención explícita "@email@dominio" en el texto si no se pasó
    import re as _re
    mencion = data.mencion
    if not mencion:
        m = _re.search(r"@([\w.+-]+@[\w-]+\.[\w.-]+)", data.texto)
        if m:
            mencion = m.group(1)

    c = ComentarioGlosaRecord(
        glosa_id=glosa_id,
        autor_email=current_user.email,
        autor_nombre=current_user.nombre or current_user.email.split("@")[0],
        autor_rol=current_user.rol,
        texto=data.texto.strip(),
        mencion=mencion,
    )
    db.add(c)
    db.commit()
    db.refresh(c)

    AuditRepository(db).registrar(
        usuario_email=current_user.email,
        usuario_rol=current_user.rol,
        accion="COMENTARIO_CREAR",
        tabla="comentarios_glosa",
        registro_id=c.id,
        detalle=f"glosa #{glosa_id} · mencion={mencion or '—'}",
    )
    return {
        "id": c.id,
        "message": "Comentario agregado",
        "mencion": mencion,
    }


@router.patch("/{comentario_id}/resolver")
def resolver(
    glosa_id: int,
    comentario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Marca el comentario como resuelto."""
    c = (
        db.query(ComentarioGlosaRecord)
        .filter(
            ComentarioGlosaRecord.id == comentario_id,
            ComentarioGlosaRecord.glosa_id == glosa_id,
        )
        .first()
    )
    if not c:
        raise HTTPException(404, "Comentario no encontrado")
    c.resuelto = 1
    c.resuelto_por = current_user.email
    c.resuelto_en = datetime.utcnow()
    db.commit()
    return {"message": "Comentario resuelto", "id": c.id}


@router.delete("/{comentario_id}")
def eliminar(
    glosa_id: int,
    comentario_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Elimina un comentario. Solo el autor, COORDINADOR o SUPER_ADMIN."""
    c = (
        db.query(ComentarioGlosaRecord)
        .filter(
            ComentarioGlosaRecord.id == comentario_id,
            ComentarioGlosaRecord.glosa_id == glosa_id,
        )
        .first()
    )
    if not c:
        raise HTTPException(404, "Comentario no encontrado")
    if c.autor_email != current_user.email and current_user.rol not in ("SUPER_ADMIN", "COORDINADOR"):
        raise HTTPException(403, "No autorizado para eliminar este comentario")
    db.delete(c)
    db.commit()
    return {"message": "Comentario eliminado"}
