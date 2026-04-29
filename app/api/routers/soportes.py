"""Endpoints para auto-descubrimiento de soportes en el share de radicación."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.models.db import UsuarioRecord
from app.services.soportes_autodiscovery_service import get_indexer

router = APIRouter(prefix="/soportes-auto", tags=["soportes-auto"])


@router.get("/factura/{numero}")
def soportes_de_factura(
    numero: str,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Devuelve los soportes detectados en disco para una factura.

    Acepta el número en cualquier formato (`HUS487523`, `HUS0000495050`,
    `495050`) — internamente se normaliza por la parte numérica.
    Reconstruye el índice automáticamente si está frío.
    """
    if not numero or len(numero) < 3:
        raise HTTPException(400, "Número de factura inválido")
    indexer = get_indexer()
    soportes = indexer.lookup(numero)
    return {
        "factura": numero,
        "soportes": soportes,
        "total": len(soportes),
        "tipos_detectados": sorted({s["tipo"] for s in soportes}),
    }


@router.get("/stats")
def stats(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Estado del indexador: raíz, archivos indexados, último build, errores."""
    return get_indexer().stats()


@router.post("/reindex")
def reindex(
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Fuerza una reconstrucción del índice. Solo auditor o superior.

    Conviene correrlo manualmente cuando se acaba de cargar un mes nuevo
    de soportes y no se quiere esperar al TTL automático.
    """
    return get_indexer().rebuild()
