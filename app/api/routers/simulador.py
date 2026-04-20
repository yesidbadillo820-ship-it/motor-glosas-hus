"""Simulador de conciliación con IA.

Antes de ir a la audiencia, IA actúa como abogado de la EPS y plantea
las 3 contra-argumentaciones más probables a la postura de HUS. Sugiere
cómo responder a cada una.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.db import ConciliacionRecord, GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual, get_auditor_o_superior
from app.services.glosa_service import GlosaService
from app.core.config import get_settings
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/conciliaciones/{conciliacion_id}/simulador", tags=["simulador"])


class SimuladorInput(BaseModel):
    postura_hus: str = Field(..., min_length=20, max_length=20000)


@router.post("/")
async def simular(
    conciliacion_id: int,
    data: SimuladorInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_auditor_o_superior),
):
    """Genera simulación: contraargumentos EPS + respuestas sugeridas HUS."""
    c = db.query(ConciliacionRecord).filter(ConciliacionRecord.id == conciliacion_id).first()
    if not c:
        raise HTTPException(404, "Conciliación no encontrada")

    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == c.glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa asociada no encontrada")

    cfg = get_settings()
    service = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
        anthropic_model=cfg.anthropic_model,
        groq_model=cfg.groq_model,
    )
    if not service.groq and not service.anthropic_key:
        raise HTTPException(503, "IA no configurada para simular")

    system = (
        "Eres un auditor médico y asesor legal SENIOR de una EPS colombiana. "
        "Tu rol es PONER EN APRIETOS a la IPS que defiende una glosa. "
        "Analiza la postura del hospital y genera las 3 contra-argumentaciones "
        "más probables que la EPS podría usar en la audiencia de conciliación, "
        "con base en normativa colombiana de salud. Para cada contra-argumento, "
        "sugiere también UNA respuesta efectiva que el hospital podría dar. "
        "Sé técnico, realista y específico. Responde en el siguiente formato JSON "
        "estricto (sin preámbulo):\n\n"
        '{\n'
        '  "contraargumentos": [\n'
        '    {"titulo":"...","texto":"...","respuesta_sugerida_hus":"..."},\n'
        '    {...}, {...}\n'
        '  ],\n'
        '  "probabilidad_exito_hus": 0-100,\n'
        '  "consejo_estrategico": "..."\n'
        '}'
    )
    user = (
        f"GLOSA:\nCódigo: {glosa.codigo_glosa}\nEPS: {glosa.eps}\n"
        f"Factura: {glosa.factura}\nValor objetado: ${glosa.valor_objetado:,.0f}\n\n"
        f"POSTURA DE LA IPS EN LA AUDIENCIA:\n{data.postura_hus}\n\n"
        "Genera la simulación en el JSON solicitado."
    )

    try:
        content, modelo = await service._llamar_ia(
            system, user, eps=glosa.eps or "", codigo=glosa.codigo_glosa or ""
        )
    except Exception as e:
        raise HTTPException(500, f"Error IA: {e}")

    # Parsear JSON (tolerante a envoltorios)
    import json as _json
    import re as _re
    txt = content.strip()
    # Quitar ```json ... ``` si viene
    txt = _re.sub(r"^```(?:json)?\s*", "", txt)
    txt = _re.sub(r"\s*```$", "", txt)
    # Extraer primer objeto JSON
    m = _re.search(r"\{.*\}", txt, _re.DOTALL)
    if m:
        txt = m.group(0)

    try:
        parsed = _json.loads(txt)
    except Exception:
        # Fallback: devolver texto crudo
        parsed = {
            "contraargumentos": [
                {
                    "titulo": "Simulación sin formato estructurado",
                    "texto": content[:1500],
                    "respuesta_sugerida_hus": "",
                }
            ],
            "probabilidad_exito_hus": 0,
            "consejo_estrategico": "La IA no devolvió JSON estructurado. Revisa el texto completo.",
        }

    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="SIMULADOR_CONCILIACION", tabla="conciliaciones",
        registro_id=conciliacion_id,
        detalle=f"Modelo: {modelo}",
    )
    parsed["_modelo"] = modelo
    return parsed
