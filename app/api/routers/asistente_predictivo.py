"""Asistente Predictivo — endpoint para Ola 4 (Inteligencia Ambiental).

Recibe texto parcial mientras el gestor escribe y devuelve:
  - Códigos detectados
  - Valor objetado detectado
  - Plantilla predicha (cuál se va a usar)
  - Complejidad estimada
  - Sugerencias contextuales basadas en histórico
  - Predicción de modelo IA que se usará

El frontend llama este endpoint con debounce (200ms) mientras el gestor
escribe en el textarea, y muestra las sugerencias en tiempo real DEBAJO
del campo — sin haber hecho click en Analizar todavía.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import GlosaRecord, UsuarioRecord
from app.services.ia_router import enrutar
from app.services.inteligencia_ambiental import (
    analisis_rapido,
    generar_sugerencias_contextuales,
)

router = APIRouter(prefix="/asistente", tags=["asistente-predictivo"])


class TextoEntrada(BaseModel):
    texto: str = Field(..., min_length=1, max_length=5000)
    eps: str = ""
    proveedores_disponibles: Optional[list[str]] = None


class PrediccionResponse(BaseModel):
    codigos_detectados: list[str]
    valores_detectados: list[float]
    valor_principal: Optional[float]
    numero_factura: Optional[str]
    fecha_detectada: Optional[str]
    es_ratificacion: bool
    es_extemporanea: bool
    complejidad_estimada: str
    plantilla_predicha: Optional[dict]
    modelo_recomendado: Optional[dict]
    sugerencias: list[dict]


@router.post("/predecir", response_model=PrediccionResponse)
def predecir_dictamen(
    payload: TextoEntrada,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
) -> PrediccionResponse:
    """Análisis predictivo en tiempo real del texto que escribe el gestor.

    Llamar con debounce (200ms) mientras el usuario teclea.
    """
    # 1. Análisis del texto
    analisis = analisis_rapido(payload.texto)

    # 2. Decisión de modelo
    valor_principal = max(analisis.valores_detectados) if analisis.valores_detectados else None
    proveedores = set(payload.proveedores_disponibles) if payload.proveedores_disponibles else None
    decision = enrutar(
        eps=payload.eps,
        valor=valor_principal,
        texto_glosa=payload.texto,
        es_ratificacion=analisis.es_ratificacion,
        es_extemporanea=analisis.es_extemporanea,
        proveedores_disponibles=proveedores,
    )

    # 3. Histórico de glosas del gestor (max 50 últimas)
    historico: list[dict] = []
    try:
        codigo_principal = analisis.codigos_detectados[0] if analisis.codigos_detectados else ""
        if codigo_principal and payload.eps:
            rows = (
                db.query(GlosaRecord)
                .filter(GlosaRecord.codigo_glosa == codigo_principal.upper())
                .filter(GlosaRecord.eps.ilike(f"%{payload.eps}%"))
                .order_by(GlosaRecord.creado_en.desc())
                .limit(50)
                .all()
            )
            for r in rows:
                historico.append(
                    {
                        "eps": r.eps or "",
                        "codigo": r.codigo_glosa or "",
                        "estado": (r.estado or "").upper(),
                        "valor": float(r.valor_objetado or 0),
                        "dictamen_id": r.id,
                    }
                )
    except Exception:
        # No bloquear si la consulta falla
        pass

    sugerencias = generar_sugerencias_contextuales(
        eps=payload.eps,
        codigo=analisis.codigos_detectados[0] if analisis.codigos_detectados else "",
        valor=valor_principal,
        historico_glosas=historico,
    )

    return PrediccionResponse(
        codigos_detectados=analisis.codigos_detectados,
        valores_detectados=analisis.valores_detectados,
        valor_principal=valor_principal,
        numero_factura=analisis.numero_factura,
        fecha_detectada=analisis.fecha_detectada,
        es_ratificacion=analisis.es_ratificacion,
        es_extemporanea=analisis.es_extemporanea,
        complejidad_estimada=analisis.complejidad_estimada,
        plantilla_predicha=(
            {
                "codigo_familia": analisis.plantilla_predicha.codigo_familia,
                "plantilla_id": analisis.plantilla_predicha.plantilla_id,
                "titulo": analisis.plantilla_predicha.titulo,
                "confianza": analisis.plantilla_predicha.confianza,
                "razon": analisis.plantilla_predicha.razon,
            }
            if analisis.plantilla_predicha
            else None
        ),
        modelo_recomendado={
            "complejidad": decision.complejidad,
            "modelo": decision.modelo_recomendado,
            "fallback": decision.modelos_fallback,
            "razon": decision.razon,
            "tiempo_estimado_s": decision.tiempo_max_esperado_s,
            "costo_estimado_centavos": decision.costo_estimado_centavos,
        },
        sugerencias=[
            {
                "tipo": s.tipo,
                "titulo": s.titulo,
                "descripcion": s.descripcion,
                "accion_label": s.accion_label,
                "accion_url": s.accion_url,
                "relevancia": s.relevancia,
            }
            for s in sugerencias
        ],
    )
