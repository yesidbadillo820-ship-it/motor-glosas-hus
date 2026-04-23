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



# ─── PREDICTOR DE GLOSAS (Ronda 4) ──────────────────────────────────────────

class PredictorInput(BaseModel):
    eps: str = Field(..., min_length=2, max_length=200)
    cups: str = Field(..., min_length=1, max_length=30)
    valor_facturado: float = Field(default=0.0, ge=0)
    tipo_servicio: Optional[str] = Field(default="", max_length=100)
    tiene_autorizacion: bool = True
    tiene_historia_clinica: bool = True
    tiene_soportes: bool = True


@router.post("/predecir-glosa")
def predecir_glosa_endpoint(
    data: PredictorInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Estima la probabilidad de que una factura sea glosada antes de radicar.

    Usa histórico de glosas similares + reglas determinísticas. No consume
    tokens IA. Retorna score 0-1, nivel de riesgo, códigos probables,
    motivos y recomendaciones para mitigar.
    """
    from app.services.predictor_glosas import predecir_glosa
    return predecir_glosa(
        db=db,
        eps=data.eps,
        cups=data.cups,
        valor_facturado=data.valor_facturado,
        tipo_servicio=data.tipo_servicio or "",
        tiene_autorizacion=data.tiene_autorizacion,
        tiene_historia_clinica=data.tiene_historia_clinica,
        tiene_soportes=data.tiene_soportes,
    )


# ─── EXTRACTOR AUTOMÁTICO DE FACTURA DESDE PDF (Ronda 5) ────────────────────

from fastapi import UploadFile, File  # noqa: E402


@router.post("/extraer-factura")
async def extraer_factura_endpoint(
    archivo: UploadFile = File(...),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Sube un PDF de glosa/factura y extrae automáticamente los campos
    clave (factura, CUPS, EPS, valores, códigos de glosa, paciente).

    Primero intenta extracción nativa (pdfplumber, gratis). Si el texto
    es pobre y hay ANTHROPIC_API_KEY, usa Claude Vision como OCR. Retorna
    los campos + confianza + campos_faltantes para que el frontend sepa
    qué preguntar al usuario solo cuando falta algo.
    """
    from app.services.pdf_service import PdfService
    from app.services.extractor_factura import extraer_de_texto
    from app.core.config import get_settings

    cfg = get_settings()
    contenido = await archivo.read()
    if contenido[:4] != b"%PDF":
        raise HTTPException(400, "El archivo no es un PDF válido")
    if len(contenido) > 20_000_000:
        raise HTTPException(400, "PDF muy grande (>20 MB)")

    pdf_svc = PdfService()
    texto, metodo = await pdf_svc.extraer_con_ocr(
        contenido,
        anthropic_api_key=cfg.anthropic_api_key,
        anthropic_model=cfg.anthropic_model,
    )
    campos = extraer_de_texto(texto or "")
    campos["_metodo_extraccion"] = metodo
    campos["_texto_chars"] = len(texto or "")
    return campos


# ─── RAG de normativa (Ronda 7) ────────────────────────────────────────────

@router.get("/normativa/buscar")
def buscar_normativa(
    q: str,
    top_k: int = 5,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Búsqueda semántica TF-IDF en el catálogo normativo colombiano.

    Ejemplo: /herramientas/normativa/buscar?q=tarifa+soat+diferencia
    """
    from app.services.rag_normativa import buscar_normas
    return {"consulta": q, "resultados": buscar_normas(q, top_k=top_k)}


@router.post("/normativa/validar-citas")
def validar_citas(
    payload: dict,
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Recibe {"texto": "..."} con un dictamen y retorna qué citas
    normativas fueron verificadas contra nuestro índice vs cuáles son
    'dudosas' (posible alucinación de la IA).
    """
    from app.services.rag_normativa import validar_citas_en_dictamen
    texto = (payload or {}).get("texto", "")
    return validar_citas_en_dictamen(texto)
