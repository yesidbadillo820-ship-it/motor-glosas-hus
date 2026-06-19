"""IA Router — selecciona el modelo óptimo para cada caso.

Proveedores de DICTAMEN actualizados a Fallback de Modelos Gratuitos:
  - Groq Llama 3.3 70B: Velocidad masiva y casos simples.
  - Gemini 1.5 Flash: Ventana de contexto gigante y casos medios.
  - Cohere Command R: Razonamiento legal complejo y adherencia estricta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


Complejidad = Literal["SIMPLE", "MEDIA", "COMPLEJA"]


@dataclass
class DecisionRouter:
    complejidad: Complejidad
    modelo_recomendado: str  # "groq" | "anthropic" | "gemini" | "cohere"
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
    """Devuelve el modelo recomendado + cadena de fallbacks entre los
    proveedores activos del dictamen.

    Verdad oficial (jun-2026): solo `groq` y `anthropic` se usan para
    dictámenes. Gemini, Cohere y OpenRouter están RETIRADOS — si el caller
    legacy los pasa en `proveedores_disponibles`, se ignoran silenciosamente
    (no se recomiendan ni entran al fallback).
      • COMPLEJA → anthropic (Claude razonamiento profundo); fallback groq.
      • SIMPLE   → groq (speed); fallback anthropic.
      • MEDIA    → groq (balance); fallback anthropic.
    """

    # Filtrar a los activos. Lo que venga fuera de este set se descarta.
    _ACTIVOS = {"groq", "anthropic"}
    dispo_in = proveedores_disponibles or _ACTIVOS
    disponibles = {p for p in dispo_in if p in _ACTIVOS}
    if not disponibles:
        # Ningún proveedor válido: forzamos groq como último recurso.
        disponibles = {"groq"}

    if complejidad == "COMPLEJA":
        # Claude lidera razonamiento legal complejo; si no está, caemos a groq.
        preferido = "anthropic" if "anthropic" in disponibles else "groq"
        fallback = [m for m in ("groq", "anthropic") if m in disponibles and m != preferido]
        return DecisionRouter(
            complejidad="COMPLEJA",
            modelo_recomendado=preferido,
            modelos_fallback=fallback,
            razon="Glosa compleja → Razonamiento profundo (Claude)",
            tiempo_max_esperado_s=20,
            costo_estimado_centavos=0,
        )

    if complejidad == "SIMPLE":
        # Groq (Llama) es el rey de la speed; si no está, caemos a anthropic.
        preferido = "groq" if "groq" in disponibles else "anthropic"
        fallback = [m for m in ("groq", "anthropic") if m in disponibles and m != preferido]
        return DecisionRouter(
            complejidad="SIMPLE",
            modelo_recomendado=preferido,
            modelos_fallback=fallback,
            razon="Glosa simple → Velocidad máxima (Groq, max speed)",
            tiempo_max_esperado_s=5,
            costo_estimado_centavos=0,
        )

    # MEDIA (default): groq por balance, fallback anthropic.
    preferido = "groq" if "groq" in disponibles else "anthropic"
    fallback = [m for m in ("groq", "anthropic") if m in disponibles and m != preferido]
    return DecisionRouter(
        complejidad="MEDIA",
        modelo_recomendado=preferido,
        modelos_fallback=fallback,
        razon="Glosa estándar → Balance perfecto (Groq)",
        tiempo_max_esperado_s=10,
        costo_estimado_centavos=0,
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
