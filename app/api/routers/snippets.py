"""Snippets: atajos de texto rápido para el redactor de glosas.

20-08-2026. Este archivo era un cascarón: solo `GET /snippets` devolviendo
lista vacía, con el comentario «hasta que se implemente la funcionalidad
completa». Mientras tanto la pantalla «Gestionar mis snippets» ya estaba hecha
y llamaba a tres rutas que no existían —crear, borrar y registrar uso—, así
que el auditor abría el gestor, escribía su atajo, guardaba… y le salía
«Falló». La tabla en la base de datos también estaba completa desde el
principio.

La lógica vive en `app/services/snippets_service.py`; acá solo se recibe, se
valida y se responde.
"""

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services import snippets_service

router = APIRouter(prefix="/snippets", tags=["snippets"])


class SnippetNuevo(BaseModel):
    atajo: str = Field(..., max_length=60, description="Atajo, ej. «/ratif»")
    contenido: str = Field(..., description="Texto en el que se expande el atajo")
    descripcion: str = Field("", max_length=200)
    visibilidad: str = Field("PRIVADO", description="PRIVADO | EQUIPO | GLOBAL")


@router.get("")
def listar_snippets(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> list:
    """Los snippets propios más los que el equipo o la institución comparten."""
    return snippets_service.listar(db, current_user.email)


@router.post("")
def crear_snippet(
    datos: SnippetNuevo,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> dict:
    """Crea un atajo del usuario."""
    snippet, error = snippets_service.crear(
        db,
        email=current_user.email,
        atajo=datos.atajo,
        contenido=datos.contenido,
        descripcion=datos.descripcion,
        visibilidad=datos.visibilidad,
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return snippet


@router.delete("/{snippet_id}")
def borrar_snippet(
    snippet_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> dict:
    """Borra un atajo propio."""
    ok, error = snippets_service.borrar(db, email=current_user.email, snippet_id=snippet_id)
    if not ok:
        raise HTTPException(status_code=404 if "no existe" in error else 403, detail=error)
    return {"ok": True}


@router.post("/{snippet_id}/usar")
def registrar_uso_snippet(
    snippet_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> dict:
    """Suma uno al contador de uso; es lo que ordena la lista.

    La pantalla llama esto sin esperar respuesta, así que nunca se le devuelve
    un error: que el contador falle no puede estropearle la escritura a nadie.
    """
    registrado = snippets_service.registrar_uso(db, email=current_user.email, snippet_id=snippet_id)
    return {"ok": registrado}
