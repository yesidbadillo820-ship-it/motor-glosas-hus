"""Chat conversacional sobre una glosa específica (Ronda 8).

El gestor puede "hablar" con la IA sobre un dictamen ya generado:
  - "¿Por qué citas el Art. 871?"
  - "Hazlo más corto"
  - "Cambia el tono a firme"
  - "Añade cita a la Sentencia T-760 de 2008"

Arquitectura:
  POST /chat-glosa/{glosa_id}/mensaje
    body: {texto: "...", historial: [{role, content}, ...]}
    response: {respuesta: "...", nuevo_dictamen: "..." (si aplicó cambio)}

El backend detecta si el usuario pide MODIFICAR el dictamen (verbos como
'hazlo', 'cambia', 'agrega', 'quita', 'ajusta', 'reescribe', 'refuerza')
→ usa el endpoint de refinar existente. Si solo es PREGUNTAR (por qué,
explica, qué significa) → responde sin modificar la BD.

La conversación no persiste (efímera, solo en la UI) para no inflar BD.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.services.rate_limit_ia import consumir_cupo_ia as _consumir_cupo_ia

router = APIRouter(prefix="/chat-glosa", tags=["chat-glosa"])


VERBOS_MODIFICAR = re.compile(
    r"\b(hazlo|haz|cambia|cámbialo|cambialo|agrega|añade|añadir|quita|remueve|"
    r"elimina|ajusta|reescribe|re-escribe|refuerza|acorta|acortalo|alarga|"
    r"mejora|corrige|enfatiza|simplifica|resume|actualiza|modifica|recorta)\b",
    re.IGNORECASE,
)


class ChatMensajeIn(BaseModel):
    texto: str = Field(..., min_length=2, max_length=1000)
    historial: Optional[list[dict]] = Field(default=None, max_length=10)


def _es_modificacion(texto: str) -> bool:
    return bool(VERBOS_MODIFICAR.search(texto or ""))


def _respuesta_rapida(texto: str, glosa: GlosaRecord) -> str:
    """Respuestas determinísticas para preguntas comunes (sin IA).

    Cubre lo más frecuente para ahorrar tokens.
    """
    t = (texto or "").lower()
    # Detectar preguntas: "por qué / porque / explica / qué es / que es / cuál es"
    es_pregunta = any(k in t for k in (
        "por qué", "porque", "explica", "explicame", "explícame",
        "qué es", "que es", "qué significa", "que significa",
        "cuál es", "cual es",
    ))
    if es_pregunta:
        if "871" in t or "comercio" in t:
            return (
                "El Art. 871 del Código de Comercio se cita porque establece "
                "el principio de buena fe contractual: 'Los contratos deberán "
                "celebrarse y ejecutarse de buena fe'. En controversias tarifarias "
                "es la base para decir que la EPS no puede desconocer "
                "unilateralmente el valor pactado."
            )
        if "1602" in t or "civil" in t:
            return (
                "El Art. 1602 del Código Civil es la norma general que dice "
                "'Todo contrato legalmente celebrado es una ley para los "
                "contratantes'. Se invoca para reforzar que el contrato "
                "firmado con la EPS obliga a ambas partes."
            )
        if "57" in t and ("1438" in t or "ley" in t):
            return (
                "El Art. 57 de la Ley 1438/2011 fija los plazos de la controversia "
                "de glosa: 30 días hábiles para que la EPS responda tras la "
                "respuesta de la IPS. Si no responde, opera el silencio "
                "positivo a favor del prestador."
            )
        if "2284" in t:
            return (
                "La Res. 2284/2023 es el Manual Único de Glosas y Devoluciones "
                "del MinSalud. Define los códigos TAXATIVOS (TA, SO, FA...) "
                "que la EPS puede usar y las causales de cada uno."
            )
        if "uvb" in t or "047" in t:
            return (
                "La UVB (Unidad de Valor Básico) 2026 vale $12.110 (Res. "
                "MinHacienda 31/12/2025). La Circular 047/2025 MinSalud "
                "indexó el Manual SOAT 2026 a UVB. Fórmula: "
                "Tarifa_UVB × $12.110 → centena más próxima."
            )
        if "054" in t:
            return (
                "La Resolución 054 de 2026 ESE HUS es el listado unificado de "
                "tarifas institucionales del hospital. Aplica cuando el contrato "
                "con la EPS dice 'TIPO TARIFA = PROPIAS'. Se complementa con la "
                "Res. 124/2026 que agrega nuevos códigos."
            )
    if "plazo" in t:
        return (
            "Plazos del Art. 57 Ley 1438/2011 operacionalizados por el "
            "Manual Único (Res. 2284/2023): la EPS tiene 20 días hábiles "
            "para formular la glosa, la IPS 15 días hábiles para responder, "
            "y la EPS 10 días hábiles para pronunciarse sobre la respuesta. "
            "Pasado ese plazo sin respuesta, opera el silencio favorable al "
            "prestador (levantamiento tácito)."
        )
    if "silencio" in t:
        return (
            "El silencio administrativo favorable ocurre cuando la EPS no "
            "responde en el plazo legal (Art. 57 Ley 1438/2011 y Art. 56 "
            "para la aceptación tácita de glosa extemporánea). Es una "
            "herramienta fuerte para cobrar lo facturado."
        )
    return ""


@router.post("/{glosa_id}/mensaje")
async def enviar_mensaje(
    glosa_id: int,
    data: ChatMensajeIn,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
    _cupo_ia: None = Depends(_consumir_cupo_ia),
):
    """Procesa un mensaje del gestor sobre una glosa.

    Modo de respuesta:
      1) Respuesta rápida determinística (sin IA) si la pregunta es típica
      2) Si es solicitud de MODIFICAR → delega al refinar existente
      3) Sino, responde con texto breve basado en el dictamen actual
    """
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")

    texto = (data.texto or "").strip()
    if not texto:
        raise HTTPException(400, "Mensaje vacío")

    # 1) Respuesta rápida gratis
    rapida = _respuesta_rapida(texto, glosa)
    if rapida:
        return {
            "respuesta": rapida,
            "tipo": "instantanea",
            "modifico_dictamen": False,
        }

    # 2) ¿Es una solicitud de modificar?
    if _es_modificacion(texto):
        # Delegamos al refinar. Usamos el mensaje tal cual como instrucción.
        try:
            from app.services.glosa_service import GlosaService
            # Construir servicio manualmente (no tenemos Depends en este contexto)
            from app.core.config import get_settings
            cfg = get_settings()
            svc = GlosaService(
                groq_api_key=cfg.groq_api_key,
                anthropic_api_key=cfg.anthropic_api_key,
                primary_ai=cfg.primary_ai,
            )
            nuevo = await svc.refinar_dictamen(
                dictamen_actual_html=glosa.dictamen or "",
                mensaje_usuario=texto,
                eps=glosa.eps or "",
                codigo=glosa.codigo_glosa or "",
            )
            if nuevo:
                # NO guardamos automáticamente — el usuario puede decidir
                return {
                    "respuesta": "Dictamen refinado. Revisa el preview y confirma si querés guardarlo.",
                    "tipo": "refinado",
                    "nuevo_dictamen": nuevo,
                    "modifico_dictamen": False,
                }
        except Exception as e:
            return {
                "respuesta": f"No pude refinar en este momento ({e}). Intentá "
                             "usar el botón 'Refinar con IA' directamente.",
                "tipo": "error",
                "modifico_dictamen": False,
            }

    # 3) Respuesta genérica corta
    return {
        "respuesta": (
            "No pude responder eso con certeza. Podés probar preguntas como: "
            "'¿Por qué citas el Art. 871?', '¿Cuál es el plazo?', 'Hazlo más "
            "corto', 'Cambia el tono a firme', 'Agrega cita a la Sentencia T-760'."
        ),
        "tipo": "fallback",
        "modifico_dictamen": False,
    }
