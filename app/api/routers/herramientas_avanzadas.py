"""Endpoints: multi-concepto, detector masa, simulador, learning loop."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.api.deps import get_usuario_actual
from app.database import get_db
from app.models.db import UsuarioRecord, GlosaRecord
from app.services.multi_concepto import (
    detectar_caso_multi_concepto,
    detectar_glosas_en_masa,
)

router = APIRouter(prefix="/herramientas", tags=["herramientas-avanzadas"])


class AnalisisTextoRequest(BaseModel):
    texto: str = Field(..., min_length=3, max_length=10000)


@router.post("/multi-concepto")
def analizar_multi_concepto(
    req: AnalisisTextoRequest,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Detecta si una glosa tiene múltiples códigos y recomienda abordaje."""
    return detectar_caso_multi_concepto(req.texto)


@router.get("/detector-masa")
def detector_glosas_masa(
    dias_atras: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Detecta glosas duplicadas/similares que podrían responderse en bulk."""
    from datetime import datetime, timedelta
    desde = datetime.now() - timedelta(days=dias_atras)
    glosas = db.query(GlosaRecord).filter(GlosaRecord.created_at >= desde).limit(1000).all()
    datos = [
        {
            "id": g.id,
            "codigo": g.codigo_glosa or "",
            "eps": g.eps or "",
            "texto_glosa": g.texto_glosa or "",
        }
        for g in glosas
    ]
    grupos = detectar_glosas_en_masa(datos)
    return {
        "total_glosas_analizadas": len(datos),
        "grupos_encontrados": len(grupos),
        "grupos": grupos,
    }


class SimuladorRequest(BaseModel):
    texto_glosa: str
    codigo_glosa: str = ""
    eps: str = ""
    escenario: str = Field(..., description="'con_contrato' | 'con_pdf' | 'extemporanea' | 'ratificacion'")


@router.post("/simulador")
def simulador_que_pasaria_si(
    req: SimuladorRequest,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Simula cómo cambiaría el riesgo de ratificación con distintos escenarios."""
    from app.services.riesgo_ratificacion import calcular_riesgo

    escenarios_cfg = {
        "con_contrato": {
            "label": "Si existiera contrato pactado",
            "params": {"tiene_contrato": True, "tiene_pdf_soportes": False,
                       "es_extemporanea": False, "es_ratificacion": False},
        },
        "con_pdf": {
            "label": "Si se adjuntara historia clínica completa",
            "params": {"tiene_contrato": False, "tiene_pdf_soportes": True,
                       "es_extemporanea": False, "es_ratificacion": False},
        },
        "extemporanea": {
            "label": "Si fuera extemporánea",
            "params": {"tiene_contrato": False, "tiene_pdf_soportes": False,
                       "es_extemporanea": True, "es_ratificacion": False},
        },
        "ratificacion": {
            "label": "Si fuera ratificación (segunda vuelta)",
            "params": {"tiene_contrato": False, "tiene_pdf_soportes": False,
                       "es_extemporanea": False, "es_ratificacion": True},
        },
        "todo_favorable": {
            "label": "Escenario óptimo (contrato + PDF + soportes)",
            "params": {"tiene_contrato": True, "tiene_pdf_soportes": True,
                       "es_extemporanea": False, "es_ratificacion": False},
        },
    }
    cfg = escenarios_cfg.get(req.escenario)
    if not cfg:
        raise HTTPException(status_code=400, detail=f"Escenario no válido: {req.escenario}")
    riesgo = calcular_riesgo(
        codigo_glosa=req.codigo_glosa,
        eps=req.eps,
        texto_glosa=req.texto_glosa,
        **cfg["params"],
    )
    return {
        "escenario": req.escenario,
        "label": cfg["label"],
        "riesgo": riesgo,
    }


@router.get("/learning/mis-patrones")
def learning_mis_patrones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Analiza los refinamientos que ha hecho el usuario para detectar patrones.

    Retorna estadísticas sobre qué tipo de cambios hace más frecuentemente
    el usuario (ej. 'acorta párrafos', 'agrega citas', 'suaviza tono').
    Esto permite iterar el prompt base con base en preferencias reales.
    """
    try:
        from app.models.db import VersionDictamenRecord as VersionRecord
    except ImportError:
        return {"disponible": False, "mensaje": "Feature de versionado no disponible"}

    # Consultar versiones creadas por el usuario actual en últimos 90 días
    from datetime import datetime, timedelta
    desde = datetime.now() - timedelta(days=90)
    try:
        versiones = (
            db.query(VersionRecord)
            .filter(VersionRecord.creado_por == current_user.email)
            .filter(VersionRecord.created_at >= desde if hasattr(VersionRecord, "created_at") else True)
            .all()
        )
    except Exception:
        versiones = []

    # Análisis heurístico de patrones
    patrones = {
        "total_refinamientos": len(versiones),
        "ventana_dias": 90,
        "tendencias": [],
    }

    if len(versiones) >= 3:
        # Heurísticas simples sobre motivos registrados
        motivos = []
        for v in versiones:
            m = ""
            if hasattr(v, "notas") and v.notas:
                m = v.notas
            elif hasattr(v, "motivo") and v.motivo:
                m = v.motivo
            elif hasattr(v, "mensaje_refinar") and v.mensaje_refinar:
                m = v.mensaje_refinar
            motivos.append(str(m).upper())

        cuenta_acortar = sum(1 for m in motivos if "CORT" in m or "RESUM" in m or "MENOS PALABRAS" in m)
        cuenta_citar = sum(1 for m in motivos if "CIT" in m or "NORMA" in m or "ART" in m)
        cuenta_tono = sum(1 for m in motivos if "TONO" in m or "SUAV" in m or "FIRM" in m or "CONCILIADOR" in m)
        cuenta_ampliar = sum(1 for m in motivos if "AMPLIA" in m or "EXTIENDE" in m or "MAS DETAL" in m)
        cuenta_clinico = sum(1 for m in motivos if "CLINIC" in m or "HC" in m or "HISTORIA CLIN" in m or "FOLIO" in m)

        if cuenta_acortar > 1:
            patrones["tendencias"].append({
                "patron": "Prefiere respuestas más cortas",
                "frecuencia": cuenta_acortar,
                "sugerencia_prompt": "Target de longitud reducido a 180-220 palabras cuando la complejidad es BAJA.",
            })
        if cuenta_ampliar > 1:
            patrones["tendencias"].append({
                "patron": "Prefiere respuestas más extensas",
                "frecuencia": cuenta_ampliar,
                "sugerencia_prompt": "Target de longitud ampliado a 300-350 palabras con más ejemplos.",
            })
        if cuenta_citar > 1:
            patrones["tendencias"].append({
                "patron": "Le gusta reforzar citas normativas",
                "frecuencia": cuenta_citar,
                "sugerencia_prompt": "Incrementar número de citas normativas (mínimo 4 por respuesta) y agregar texto literal entre comillas.",
            })
        if cuenta_tono > 1:
            patrones["tendencias"].append({
                "patron": "Ajusta el tono frecuentemente",
                "frecuencia": cuenta_tono,
                "sugerencia_prompt": "Revisar si el tono default (conciliador) es apropiado para los casos típicos de este auditor.",
            })
        if cuenta_clinico > 1:
            patrones["tendencias"].append({
                "patron": "Refuerza datos clínicos específicos (folios, HC, médicos)",
                "frecuencia": cuenta_clinico,
                "sugerencia_prompt": "Inyectar más referencias documentales del PDF (folios, firmas, fechas) en el prompt.",
            })

    return patrones
