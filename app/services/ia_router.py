"""IA Router — selecciona el modelo óptimo para cada caso.

Cada modelo tiene fortalezas:
  - Claude Sonnet 4.5: razonamiento jurídico complejo, redacción formal
  - Gemini 2.0 Flash: extracción multimodal de PDFs, clasificación rápida
  - Groq Llama 3.3: velocidad masiva, batches

Esta función decide cuál usar según la complejidad de la glosa.

Reglas de clasificación (mayo 2026, Plan Transformación):
  COMPLEJA → Claude:
    - Valor > $1M
    - Multi-código (>= 2 códigos detectados)
    - Es ratificación o extemporánea
    - Texto > 800 chars
  MEDIA → Groq (default):
    - Cualquier glosa estándar TA/SO/CO/FA/CL con valor < $1M
  SIMPLE → Groq + cache agresivo:
    - Glosas conocidas (mismo eps+codigo+valor que dictamen previo cached)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


Complejidad = Literal["SIMPLE", "MEDIA", "COMPLEJA"]


@dataclass
class DecisionRouter:
    complejidad: Complejidad
    modelo_recomendado: str  # "groq", "anthropic", "gemini"
    modelos_fallback: list[str]
    razon: str
    tiempo_max_esperado_s: int  # estimación para frontend SSE
    costo_estimado_centavos: int  # estimación


def clasificar_complejidad(
    *,
    valor: float | None = None,
    texto_glosa: str = "",
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    eps_familia_critica: bool = False,
    tiene_soportes_pdf: bool = False,
) -> Complejidad:
    """Clasifica la glosa por dificultad esperada."""
    # Reglas para COMPLEJA (cualquiera dispara)
    if es_ratificacion or es_extemporanea:
        return "COMPLEJA"
    if valor is not None and valor >= 1_000_000:
        return "COMPLEJA"
    if eps_familia_critica:
        return "COMPLEJA"

    # Multi-código en el texto
    codigos = re.findall(r"\b(?:TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b", texto_glosa.upper())
    if len(set(codigos)) >= 2:
        return "COMPLEJA"

    if len(texto_glosa) > 800:
        return "COMPLEJA"

    # SIMPLE si tiene soportes y es valor bajo
    if tiene_soportes_pdf and (valor or 0) < 200_000:
        return "SIMPLE"

    return "MEDIA"


def elegir_modelo(
    complejidad: Complejidad,
    *,
    proveedores_disponibles: set[str] | None = None,
) -> DecisionRouter:
    """Devuelve el modelo recomendado + cadena de fallbacks.

    Args:
        complejidad: SIMPLE | MEDIA | COMPLEJA
        proveedores_disponibles: set de "groq"/"anthropic"/"gemini". Si None,
            asume todos disponibles.

    Returns:
        DecisionRouter con .modelo_recomendado, .modelos_fallback, .razon, etc.
    """
    disponibles = proveedores_disponibles or {"groq", "anthropic", "gemini"}

    if complejidad == "COMPLEJA":
        # Anthropic es mejor en razonamiento legal complejo
        preferido = "anthropic" if "anthropic" in disponibles else "groq"
        fallback = [m for m in ["groq", "gemini"] if m in disponibles and m != preferido]
        return DecisionRouter(
            complejidad="COMPLEJA",
            modelo_recomendado=preferido,
            modelos_fallback=fallback,
            razon="Glosa compleja (ratificación/multi-código/alto valor) → razonamiento jurídico profundo",
            tiempo_max_esperado_s=20,
            costo_estimado_centavos=5,
        )

    if complejidad == "SIMPLE":
        # Groq es 5-10x más rápido que los demás y para glosas simples es suficiente
        preferido = "groq" if "groq" in disponibles else "anthropic"
        fallback = [m for m in ["anthropic", "gemini"] if m in disponibles and m != preferido]
        return DecisionRouter(
            complejidad="SIMPLE",
            modelo_recomendado=preferido,
            modelos_fallback=fallback,
            razon="Glosa simple con soportes claros → speed",
            tiempo_max_esperado_s=5,
            costo_estimado_centavos=1,
        )

    # MEDIA (default)
    preferido = "groq" if "groq" in disponibles else "anthropic"
    fallback = [m for m in ["anthropic", "gemini"] if m in disponibles and m != preferido]
    return DecisionRouter(
        complejidad="MEDIA",
        modelo_recomendado=preferido,
        modelos_fallback=fallback,
        razon="Glosa estándar → balance speed/calidad",
        tiempo_max_esperado_s=10,
        costo_estimado_centavos=2,
    )


def enrutar(
    *,
    eps: str = "",
    valor: float | None = None,
    texto_glosa: str = "",
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    tiene_soportes_pdf: bool = False,
    proveedores_disponibles: set[str] | None = None,
) -> DecisionRouter:
    """Clasificación + selección en un solo paso."""
    # EPS críticas (régimen especial — más sensibles a errores legales)
    eps_critica = bool(
        eps
        and any(
            crit in eps.upper()
            for crit in ("FOMAG", "PPL", "POLICIA", "FAMISANAR", "POSITIVA", "SUMIMEDICAL")
        )
    )
    comp = clasificar_complejidad(
        valor=valor,
        texto_glosa=texto_glosa,
        es_ratificacion=es_ratificacion,
        es_extemporanea=es_extemporanea,
        eps_familia_critica=eps_critica,
        tiene_soportes_pdf=tiene_soportes_pdf,
    )
    return elegir_modelo(comp, proveedores_disponibles=proveedores_disponibles)
