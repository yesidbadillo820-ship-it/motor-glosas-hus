"""Preview de auditoría — corre el auditor SIN llamar al LLM.

Permite al gestor ver QUÉ inconsistencias detecta el sistema antes
de gastar tokens del modelo. Si el score es alto y los hallazgos
son contundentes, le da confianza para usar texto fijo o ajustar
el caso antes de generar el dictamen.

Endpoint:
  POST /glosas/preview-auditoria
    body: { texto_glosa, eps?, codigo?, cups?,
            valor_facturado?, valor_pactado?, valor_objetado? }
    return: { hallazgos, score_evidencia, accion_sugerida, ... }
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord

router = APIRouter(tags=["auditor"])


class PreviewIn(BaseModel):
    texto_glosa: str = Field(..., min_length=1, max_length=5000)
    eps: Optional[str] = None
    codigo: Optional[str] = None
    cups: Optional[str] = None
    valor_facturado: Optional[float] = Field(None, ge=0)
    valor_pactado: Optional[float] = Field(None, ge=0)
    valor_objetado: Optional[float] = Field(None, ge=0)


@router.post("/glosas/preview-auditoria")
def preview_auditoria(
    body: PreviewIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Corre el auditor pre-IA. Determinístico, no consume tokens."""
    from app.services.auditor_glosa import auditar
    from app.utils.parsers_glosa import _extraer_valores_glosa

    # Auto-extraer valores del texto si no vinieron en el body.
    vals = _extraer_valores_glosa(body.texto_glosa, cups=body.cups)
    valor_facturado = float(body.valor_facturado or vals.get("facturado") or 0.0)
    valor_objetado = float(body.valor_objetado or vals.get("objetado") or 0.0)

    # Inferir contrato y tarifa pactada del catálogo.
    tiene_contrato = False
    valor_pactado = float(body.valor_pactado or 0.0)
    if body.eps:
        try:
            from app.repositories.contrato_repository import ContratoRepository
            repo = ContratoRepository(db)
            c = repo.obtener(body.eps)
            tiene_contrato = c is not None
        except Exception:
            pass
    # Si nos pasaron el cups y no hay valor_pactado, intentar inferirlo
    # del catálogo de tarifas.
    if (valor_pactado <= 0) and body.eps and body.cups:
        try:
            from app.services.tarifa_lookup_service import evaluar_glosa_tarifa
            info = evaluar_glosa_tarifa(
                db, eps=body.eps, cups=body.cups,
                valor_facturado=valor_facturado,
                valor_objetado=valor_objetado,
            )
            if info and info.get("encontrada"):
                valor_pactado = float(
                    info.get("valor_pactado_calc") or 0.0
                )
                tiene_contrato = True
        except Exception:
            pass

    a = auditar(
        body.texto_glosa,
        eps=body.eps, codigo=body.codigo, cups=body.cups,
        tiene_contrato=tiene_contrato,
        valor_facturado=valor_facturado,
        valor_pactado=valor_pactado,
        valor_objetado=valor_objetado,
    )
    return {
        "hallazgos": a["hallazgos"],
        "score_evidencia": a["score_evidencia"],
        "accion_sugerida": a["accion_sugerida"],
        "n_hallazgos_alta": a["n_hallazgos_alta"],
        "tiene_contrato_detectado": tiene_contrato,
        "valor_facturado_detectado": valor_facturado,
        "valor_objetado_detectado": valor_objetado,
        "valor_pactado_detectado": valor_pactado,
    }
