"""Endpoint para consulta de normativa colombiana en cuentas médicas."""
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.normativa_completa import (
    consultar_normativa,
    listar_todas_las_normas,
    normas_relevantes_para_codigo,
)

router = APIRouter(prefix="/consulta-normativa", tags=["consulta-normativa"])


# Ronda 48: detector de preguntas sobre homologación CUPS.
# Si el usuario pregunta "cuál es el CUPS de X" o "qué código corresponde
# al 39147B-18", respondemos directo con el homologador — antes de caer
# al índice TF-IDF de normas generales.
_PATRON_HOMOLOGACION = re.compile(
    r"(c[óo]digo\s+cups|cups|equivale|homologa|equivalencia|qu[eé]\s+c[óo]digo"
    r"|corresponde\s+a|c[oó]digo\s+oficial)",
    re.IGNORECASE,
)
# Detectamos códigos candidatos a CUPS:
#   - alfanuméricos (al menos 1 letra): 39147B-18, 890348H, FMQ6296
#   - o al menos 5 dígitos consecutivos (CUPS oficial): 890348, 372301
# Esto evita que años sueltos (2025, 2641) se confundan con CUPS.
_PATRON_CODIGO_EN_PREGUNTA = re.compile(
    r"\b("
    r"[A-Z]{1,3}\d{3,8}[A-Z]?\d{0,2}(?:-\d{1,3})?"   # con prefijo letra (FMQ6296)
    r"|\d{5,8}[A-Z]\d{0,2}(?:-\d{1,3})?"              # dígitos + sufijo letra (890348H, 39147B-18)
    r"|\d{5,8}(?:-\d{1,3})?"                           # solo dígitos ≥5 (890348, 872801)
    r")\b"
)

# Contextos de palabras que indican que un número es de norma, no de CUPS.
_CONTEXTO_NORMA = re.compile(
    r"(LEY|RESOLUCI[ÓO]N|RESOLUCION|DECRETO|CIRCULAR|ACUERDO|SENTENCIA|ART[ÍI]CULO|ART\.)\s+\d",
    re.IGNORECASE,
)


class ConsultaRequest(BaseModel):
    pregunta: str = Field(..., min_length=3, description="Pregunta del auditor")
    limite: int = Field(5, ge=1, le=20)


def _intentar_homologacion(pregunta: str, db: Session) -> dict | None:
    """Si la pregunta es sobre un CUPS/código, usa el homologador."""
    if not _PATRON_HOMOLOGACION.search(pregunta):
        return None
    # Remover menciones de normas (Ley 1438, Resolución 2641, Art. 57...)
    # para que sus números no se confundan con CUPS.
    limpia = _CONTEXTO_NORMA.sub(" ", pregunta)
    codigos = _PATRON_CODIGO_EN_PREGUNTA.findall(limpia)
    # Filtrar códigos de glosa (TA0201, SO0101...) — no son CUPS
    codigos = [
        c for c in codigos
        if not re.match(r"^(TA|SO|FA|CO|CL|PE|AU|IN|ME|SE|EX)\d{2,4}$", c)
    ]
    if not codigos:
        return None
    # Intentar homologar el primero
    from app.services.homologador_cups import cita_res_2641, homologar_cups

    for cod in codigos:
        info = homologar_cups(cod, db=db)
        if info:
            return {
                "tipo": "homologacion_cups",
                "codigo_consultado": cod,
                "cups_oficial": info["cups_oficial"],
                "descripcion": info.get("descripcion", ""),
                "fuente": info.get("fuente", ""),
                "confianza": info.get("confianza", "alta"),
                "cita_formal": cita_res_2641(cod, info["cups_oficial"]),
            }
    return None


@router.post("")
def consultar(
    req: ConsultaRequest,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Consulta normativa vigente sobre cuentas médicas, glosas, facturación, etc.

    Ejemplos:
    - "¿qué dice el Art. 57 de la Ley 1438?"
    - "¿cuál es el plazo para formular una glosa?"
    - "¿cuál es el CUPS de 39147B-18?" (usa el homologador Res. 2641/2025)
    """
    # Ronda 48: primero intentar homologación CUPS si la pregunta es sobre un código
    homo = _intentar_homologacion(req.pregunta, db)

    resultados = consultar_normativa(req.pregunta, limite=req.limite)
    return {
        "pregunta": req.pregunta,
        "homologacion_cups": homo,
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
