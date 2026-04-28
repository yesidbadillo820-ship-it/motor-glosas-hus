"""Detector "REQUIERE_SOPORTES" — gating gratis sin tokens.

Antes de gastar tokens del LLM en una glosa, evalúa si la información
disponible (texto + PDFs) es suficiente para un dictamen útil.
Si no lo es, marca la glosa como REQUIERE_SOPORTES y el motor
NO la procesa hasta que el gestor suba los PDFs faltantes.

Filosofía:
  • Determinístico, cero LLM.
  • Conservador: prefiere mandar al gestor a complementar antes que
    generar un dictamen "REVISAR" genérico que no le sirve.
  • Cada caso devuelve (bool, motivo) para que la UI muestre al
    gestor QUÉ falta.

Reglas:
  • Texto demasiado corto (< 50 chars) → REQUIERE_SOPORTES.
  • Texto = "Glosa importada desde recepción..." (placeholder de
    importación masiva sin enriquecer) → REQUIERE_SOPORTES.
  • Código SO* (Soportes) y NO hay PDFs adjuntos → REQUIERE_SOPORTES.
  • Código AU* (Autorización) sin número de autorización ni PDFs →
    REQUIERE_SOPORTES.
  • Valor objetado >= $1M y texto + PDF muy escasos → REQUIERE_SOPORTES.
  • CL/PE (pertinencia clínica) sin contexto clínico → REQUIERE_SOPORTES.
"""
from __future__ import annotations

import re
from typing import Optional


# Marcadores típicos de glosa "vacía" importada masiva
_FRASES_PLACEHOLDER = (
    "GLOSA IMPORTADA DESDE RECEPCIÓN",
    "GLOSA IMPORTADA DESDE RECEPCION",
    "PENDIENTE DE ANÁLISIS",
    "PENDIENTE DE ANALISIS",
    "PENDIENTE DEL GESTOR",
)


def evaluar(
    *,
    codigo_glosa: Optional[str],
    texto_glosa: Optional[str],
    contexto_pdf: Optional[str] = "",
    valor_objetado: float = 0.0,
    cups: Optional[str] = None,
    numero_autorizacion: Optional[str] = None,
) -> dict:
    """Evalúa si la glosa requiere soportes adicionales antes de procesarla.

    Retorna:
      {
        "requiere": bool,
        "motivo": str (descripción legible),
        "soportes_sugeridos": list[str],
        "puede_procesar_ia": bool,
      }
    """
    texto = (texto_glosa or "").strip()
    pdf = (contexto_pdf or "").strip()
    codigo = (codigo_glosa or "").strip().upper()
    pref = codigo[:2] if len(codigo) >= 2 else ""

    texto_upper = texto.upper()

    # Regla 1: texto vacío o solo placeholder
    if len(texto) < 50:
        return {
            "requiere": True,
            "motivo": (
                "El texto de la glosa es muy corto para generar un "
                "dictamen útil. Necesitamos el detalle de la objeción "
                "del Excel DGH."
            ),
            "soportes_sugeridos": [
                "Texto detallado de la glosa según el Excel del DGH",
            ],
            "puede_procesar_ia": False,
        }

    if any(p in texto_upper for p in _FRASES_PLACEHOLDER):
        return {
            "requiere": True,
            "motivo": (
                "La glosa fue importada del Excel masivo y aún no tiene "
                "el detalle de la objeción de la EPS. Se requiere el "
                "texto completo del DGH o aporte el archivo Excel del "
                "concepto específico."
            ),
            "soportes_sugeridos": [
                "Texto del concepto en el Excel DGH (campo Observación)",
            ],
            "puede_procesar_ia": False,
        }

    # Regla 2: código SO* (Soportes) sin documentos
    if pref == "SO" and len(pdf) < 500:
        return {
            "requiere": True,
            "motivo": (
                "Código SO (Soportes): la EPS objeta ausencia o "
                "inconsistencia documental. Para refutar necesitamos "
                "los soportes que ya están en el expediente."
            ),
            "soportes_sugeridos": [
                "Historia clínica institucional del paciente",
                "RIPS radicados ante la EPS",
                "Factura electrónica (FEV)",
                "Reporte del procedimiento si aplica (laboratorio, radiología, etc.)",
            ],
            "puede_procesar_ia": False,
        }

    # Regla 3: código AU* (Autorización) sin número ni PDFs
    if pref == "AU" and not numero_autorizacion and len(pdf) < 500:
        return {
            "requiere": True,
            "motivo": (
                "Código AU (Autorización): sin número de autorización "
                "ni PDFs adjuntos no se puede sostener defensa. "
                "Se requiere documentar la cobertura."
            ),
            "soportes_sugeridos": [
                "Número de autorización emitido por la EPS",
                "Solicitud de autorización radicada (con sello/fecha)",
                "Constancia de urgencia si aplica (Art. 168 Ley 100)",
            ],
            "puede_procesar_ia": False,
        }

    # Regla 4: pertinencia clínica (CL/PE) sin contexto clínico
    if pref in ("CL", "PE") and len(pdf) < 800:
        return {
            "requiere": True,
            "motivo": (
                "Código de pertinencia clínica: necesitamos la historia "
                "clínica para sostener el criterio del médico tratante."
            ),
            "soportes_sugeridos": [
                "Historia clínica con diagnóstico CIE-10 y plan de manejo",
                "Epicrisis si hubo hospitalización",
                "Notas médicas de evolución",
            ],
            "puede_procesar_ia": False,
        }

    # Regla 5: valor alto + texto/PDF escasos → casos críticos
    if valor_objetado >= 1_000_000 and len(texto) < 200 and len(pdf) < 1000:
        return {
            "requiere": True,
            "motivo": (
                f"Glosa de alta cuantía (${valor_objetado:,.0f}) sin "
                "contexto suficiente. Los casos relevantes requieren "
                "expediente completo para no exponer al hospital."
            ),
            "soportes_sugeridos": [
                "Expediente completo del paciente",
                "Factura electrónica de la atención",
                "Soportes específicos según tipo de glosa",
            ],
            "puede_procesar_ia": False,
        }

    # Caso default: información suficiente, puede procesarse con IA
    return {
        "requiere": False,
        "motivo": "Información suficiente para análisis automático",
        "soportes_sugeridos": [],
        "puede_procesar_ia": True,
    }


def mensaje_para_dictamen(evaluacion: dict, codigo_glosa: str = "") -> str:
    """Genera un dictamen-placeholder cuando la glosa requiere soportes.

    Este texto se guarda en el campo `dictamen` para que cuando el
    gestor abra la glosa, vea inmediatamente qué soportes faltan.
    """
    if not evaluacion or not evaluacion.get("requiere"):
        return ""
    motivo = evaluacion.get("motivo", "")
    soportes = evaluacion.get("soportes_sugeridos", [])
    partes = [
        "📄 GLOSA REQUIERE SOPORTES — pendiente de análisis con IA",
        "",
        f"Código: {codigo_glosa or '—'}",
        f"Motivo: {motivo}",
        "",
    ]
    if soportes:
        partes.append("Soportes que el gestor debe aportar:")
        for s in soportes:
            partes.append(f"  • {s}")
        partes.append("")
    partes.append(
        "👉 Acción del gestor: abrí esta glosa, adjuntá los soportes "
        "PDF arriba indicados y volvé a darle 'Re-analizar con IA' "
        "para generar el dictamen completo."
    )
    return "\n".join(partes)
