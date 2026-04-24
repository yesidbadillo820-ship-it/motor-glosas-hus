"""Endpoint para consulta de normativa colombiana en cuentas médicas."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord
from app.services.normativa_completa import (
    consultar_normativa,
    listar_todas_las_normas,
    normas_relevantes_para_codigo,
)

router = APIRouter(prefix="/consulta-normativa", tags=["consulta-normativa"])


class ConsultaRequest(BaseModel):
    pregunta: str = Field(..., min_length=3, description="Pregunta del auditor")
    limite: int = Field(5, ge=1, le=20)


@router.post("")
def consultar(
    req: ConsultaRequest,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Consulta normativa vigente sobre cuentas médicas, glosas, facturación, etc.

    Ejemplos:
    - "¿qué dice el Art. 57 de la Ley 1438?"
    - "¿cuál es el plazo para formular una glosa?"
    - "¿qué norma regula la historia clínica?"
    """
    resultados = consultar_normativa(req.pregunta, limite=req.limite)
    return {
        "pregunta": req.pregunta,
        "total_encontrados": len(resultados),
        "resultados": resultados,
    }


@router.get("/normas")
def listar_normas(
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Lista todas las normas indexadas en la biblioteca."""
    return {
        "total": len(listar_todas_las_normas()),
        "normas": listar_todas_las_normas(),
    }


@router.get("/por-codigo/{codigo}")
def normas_por_codigo_glosa(
    codigo: str,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Retorna las normas más relevantes a citar para un código de glosa (TA0801, FA0202, etc.)."""
    normas = normas_relevantes_para_codigo(codigo)
    detalles = []
    from app.services.normativa_completa import _TODAS_LAS_NORMAS
    for clave in normas:
        n = _TODAS_LAS_NORMAS.get(clave)
        if n:
            detalles.append({
                "clave": clave,
                "nombre": n["nombre"],
                "titulo": n.get("titulo", ""),
                "aplicacion": n.get("notas", n.get("ratio", "")),
            })
    return {
        "codigo_glosa": codigo,
        "normas_sugeridas": detalles,
    }
