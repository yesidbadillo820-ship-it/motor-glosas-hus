"""Snippets: atajos de texto rápido para el redactor de glosas.

Endpoint mínimo que evita 404 en el frontend. Devuelve lista vacía
hasta que se implemente la funcionalidad completa de snippets.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/snippets", tags=["snippets"])


@router.get("")
def listar_snippets() -> list:
    """Devuelve la lista de snippets disponibles (por ahora vacía)."""
    return []
