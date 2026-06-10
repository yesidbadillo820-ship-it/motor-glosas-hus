"""IA Router — selecciona el modelo óptimo para cada caso.

Proveedores de DICTAMEN (jun-2026, decisión Yesid — Gemini y OpenRouter
retirados del dictamen; Gemini quedó solo como OCR de PDFs escaneados):
  - Claude Sonnet 4.x: razonamiento jurídico complejo, redacción formal
  - Groq Llama 3.3: velocidad masiva, batches (primario)

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
    modelo_recomendado: str  # "groq" | "anthropic"
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
    codigo_glosa: str = "",
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

    # Texto libre (sin código AA#### ni en el texto ni como parámetro):
    # la familia se infiere por keywords con fallback genérico y no hay
    # plantilla exacta que guíe al modelo — el caso más difícil, no el
    # más fácil. Evaluación de estrés 10-jun-2026: las 5 glosas de texto
    # libre que cayeron a Groq promediaron 2.2/10 (cláusulas fabricadas,
    # enumeraciones rotas) vs 7.7/10 de las que tomó Claude.
    codigo_param = (codigo_glosa or "").strip().upper()
    codigo_param_valido = bool(
        re.fullmatch(r"(?:TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}", codigo_param)
    )
    if texto_glosa and not codigos and not codigo_param_valido:
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
        proveedores_disponibles: set de "groq"/"anthropic". Si None, asume
            ambos disponibles. Proveedores retirados del dictamen
            ("gemini"/"openrouter") se ignoran aunque el caller los pase.

    Returns:
        DecisionRouter con .modelo_recomendado, .modelos_fallback, .razon, etc.
    """
    # Filtro duro: el dictamen solo puede salir de Groq o Anthropic
    # (jun-2026). Si un caller legacy pasa "gemini"/"openrouter", se
    # descartan en silencio.
    disponibles = (proveedores_disponibles or {"groq", "anthropic"}) & {"groq", "anthropic"}

    if complejidad == "COMPLEJA":
        # Anthropic es mejor en razonamiento legal complejo
        preferido = "anthropic" if "anthropic" in disponibles else "groq"
        fallback = [m for m in ["groq"] if m in disponibles and m != preferido]
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
        fallback = [m for m in ["anthropic"] if m in disponibles and m != preferido]
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
    fallback = [m for m in ["anthropic"] if m in disponibles and m != preferido]
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
    codigo_glosa: str = "",
) -> DecisionRouter:
    """Clasificación + selección en un solo paso."""
    # EPS críticas (régimen especial — más sensibles a errores legales).
    # Auditoría 10-jun-2026 P1-5: la lista no incluía la sanidad militar/
    # policial (DISPENSARIO/DIGSA/DMBUG) — el contrato 440-DIGSA/DMBUG-2025
    # con cláusulas reales cargadas se enrutaba a Groq, que fabricó
    # "cláusula 12" inexistente. Todo régimen especial es crítico.
    eps_critica = bool(
        eps
        and any(
            crit in eps.upper()
            for crit in (
                "FOMAG",
                "PPL",
                "POLICIA",
                "POLICÍA",
                "FAMISANAR",
                "POSITIVA",
                "SUMIMEDICAL",
                "DISPENSARIO",
                "DIGSA",
                "DMBUG",
                "SANIDAD",
                "MILITAR",
                "EJERCITO",
                "EJÉRCITO",
                "ARMADA NACIONAL",
                "FUERZA AEREA",
                "FUERZA AÉREA",
            )
        )
    )
    comp = clasificar_complejidad(
        valor=valor,
        texto_glosa=texto_glosa,
        es_ratificacion=es_ratificacion,
        es_extemporanea=es_extemporanea,
        eps_familia_critica=eps_critica,
        tiene_soportes_pdf=tiene_soportes_pdf,
        codigo_glosa=codigo_glosa,
    )
    return elegir_modelo(comp, proveedores_disponibles=proveedores_disponibles)
