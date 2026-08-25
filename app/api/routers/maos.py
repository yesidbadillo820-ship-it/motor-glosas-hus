"""Material de osteosíntesis: precio institucional y defensa lista para pegar.

La EPS objeta el valor del material diciendo que «no está pactado». La
respuesta está en el Anexo 09 de la Resolución 194 de 2025 —1.216 códigos con
su precio— y hasta ahora había que buscarla a ojo en un PDF de 18 páginas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.services import maos as svc

router = APIRouter(prefix="/maos", tags=["maos"])


@router.get("")
def resumen_maos(current_user: UsuarioRecord = Depends(get_usuario_actual)):
    """Qué trae el catálogo y con qué norma se defiende."""
    return svc.resumen()


@router.get("/buscar")
def buscar_maos(
    q: str = Query(..., min_length=2, description="Código FMO o parte de la descripción"),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Busca por código o por descripción.

    Por descripción porque es lo normal: la glosa de la EPS dice «tornillo
    cortical 3.5», no «FMO00482».
    """
    exacto = svc.buscar(q)
    if exacto:
        return {
            "encontrado": True,
            "por": "codigo",
            "resultados": [exacto],
            "defensa": svc.defensa_para(exacto["codigo"]),
        }
    coincidencias = svc.buscar_por_texto(q)
    return {
        "encontrado": bool(coincidencias),
        "por": "descripcion",
        "resultados": coincidencias,
        "defensa": None,
        "mensaje": (
            ""
            if coincidencias
            else f"Ningún material del Anexo 09 coincide con '{q}'. "
            "Probá con menos palabras o con el código FMO."
        ),
    }


@router.get("/defensa/{codigo}")
def defensa_maos(
    codigo: str,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """El párrafo listo para el dictamen, con el precio y su respaldo legal."""
    texto = svc.defensa_para(codigo)
    if texto is None:
        raise HTTPException(
            404,
            f"El código '{codigo}' no está en el Anexo 09 de la Resolución 194 de 2025. "
            "Verificá el código: si el material no tiene tarifa institucional, la "
            "defensa por tarifa no aplica.",
        )
    return {"codigo": svc.normalizar_codigo(codigo), "defensa": texto, "ficha": svc.buscar(codigo)}
