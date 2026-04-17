"""Búsqueda semántica (por significado, no por keyword) con Claude como
re-ranker. Útil para encontrar precedentes: 'glosas de biopsia' encuentra
aunque el código sea distinto.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual
from app.core.config import get_settings
from app.core.logging_utils import logger
from app.services.glosa_service import GlosaService

router = APIRouter(prefix="/busqueda-semantica", tags=["busqueda"])


class BusquedaInput(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    limite: int = 8


@router.post("/")
async def buscar(
    data: BusquedaInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Búsqueda semántica en historial. Combina:
    1. Preselección SQL amplia (texto + código + EPS + servicio) para reducir set
    2. Re-ranking con IA: pregunta a Claude/Groq cuáles de las N candidatas
       son las más relevantes para la consulta en lenguaje natural.
    """
    q = data.query.strip()
    limite = min(data.limite, 20)

    # 1. Preselección amplia (80 candidatos). Dividimos la query en palabras
    # para el LIKE SQL; la IA hace el resto.
    tokens = [t for t in q.lower().split() if len(t) > 2][:6]
    if not tokens:
        raise HTTPException(400, "Consulta sin términos útiles")

    from sqlalchemy import or_, and_
    conds = []
    for t in tokens:
        like = f"%{t}%"
        conds.append(or_(
            GlosaRecord.paciente.ilike(like),
            GlosaRecord.eps.ilike(like),
            GlosaRecord.codigo_glosa.ilike(like),
            GlosaRecord.factura.ilike(like),
            GlosaRecord.cups_servicio.ilike(like),
            GlosaRecord.servicio_descripcion.ilike(like),
            GlosaRecord.concepto_glosa.ilike(like),
            GlosaRecord.texto_glosa_original.ilike(like),
            GlosaRecord.dictamen.ilike(like),
        ))
    # OR entre términos (match amplio, la IA filtra después)
    candidatos = (
        db.query(GlosaRecord)
        .filter(or_(*conds))
        .order_by(GlosaRecord.creado_en.desc())
        .limit(80)
        .all()
    )

    if not candidatos:
        return {"query": q, "resultados": [], "metodo": "sin-candidatos"}

    cfg = get_settings()
    service = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
    )

    # Si no hay IA disponible, devolver la preselección por relevancia básica
    if not service.groq and not service.anthropic_key:
        resultados = [_serializar_glosa(g) for g in candidatos[:limite]]
        return {"query": q, "resultados": resultados, "metodo": "sql-only"}

    # 2. Re-ranking con IA
    snippets = []
    for g in candidatos:
        snippet = " · ".join(filter(None, [
            g.codigo_glosa or "",
            g.eps or "",
            g.factura or "",
            (g.servicio_descripcion or "")[:80],
            (g.concepto_glosa or "")[:80],
            (g.texto_glosa_original or "")[:120],
        ]))
        snippets.append(f"[{g.id}] {snippet}")

    system = (
        "Eres un asistente de búsqueda semántica para un motor de glosas médicas. "
        "Te paso una consulta en lenguaje natural y una lista de glosas. "
        "Devuelve SOLO los IDs de las glosas más relevantes a la consulta, "
        "ordenados de mayor a menor relevancia, separados por coma. "
        "Máximo " + str(limite) + " IDs. No expliques nada, solo los números."
    )
    user = (
        f"CONSULTA: {q}\n\n"
        f"GLOSAS CANDIDATAS:\n" + "\n".join(snippets[:80]) + "\n\n"
        "RESPONDE SOLO CON LOS IDS (ej: 42, 17, 88, 3)"
    )

    metodo = "sql-only"
    ids_ordenados: list[int] = []
    try:
        res, modelo = await service._llamar_ia(system, user, eps="search", codigo="")
        metodo = f"ia/{modelo}"
        # Extraer números de la respuesta
        import re as _re
        ids_ordenados = [int(n) for n in _re.findall(r"\b\d+\b", res)][:limite]
    except Exception as e:
        logger.warning(f"Busqueda semantica IA fallo: {e}. Usando SQL ranking.")

    # Mapear IDs a registros (mantiene orden IA), completa con fallback SQL
    glosa_por_id = {g.id: g for g in candidatos}
    resultados = []
    vistos = set()
    for gid in ids_ordenados:
        if gid in glosa_por_id and gid not in vistos:
            resultados.append(_serializar_glosa(glosa_por_id[gid]))
            vistos.add(gid)
        if len(resultados) >= limite:
            break
    # Si IA devolvió menos de N, completar con los primeros no vistos
    if len(resultados) < limite:
        for g in candidatos:
            if g.id not in vistos:
                resultados.append(_serializar_glosa(g))
                vistos.add(g.id)
                if len(resultados) >= limite:
                    break

    return {
        "query": q,
        "resultados": resultados,
        "metodo": metodo,
        "total_candidatos": len(candidatos),
    }


def _serializar_glosa(g: GlosaRecord) -> dict:
    return {
        "id": g.id,
        "eps": g.eps,
        "codigo_glosa": g.codigo_glosa,
        "factura": g.factura,
        "paciente": g.paciente,
        "valor_objetado": float(g.valor_objetado or 0),
        "valor_aceptado": float(g.valor_aceptado or 0),
        "servicio": g.servicio_descripcion,
        "concepto": g.concepto_glosa,
        "cups": g.cups_servicio,
        "estado": g.estado,
        "workflow_state": g.workflow_state,
        "creado_en": g.creado_en.isoformat() if g.creado_en else None,
    }
