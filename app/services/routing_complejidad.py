"""Detector compartido de COMPLEJIDAD para enrutar a Claude (Anthropic).

Creado en ronda 17 (26-jun-2026) tras detectar que el detector original
de R-CEREBRO #5 (glosa_service.py:~4290) NO se aplicaba en 3 caminos
críticos del motor:
  1. Quality Gate adapter (cuando QUALITY_GATE_ENABLED=1)
  2. Secciones de códigos adicionales en multi-código
  3. Refinamiento por instrucción del auditor (chat_glosa)

Este módulo expone:
  - PALABRAS_CLAVE_COMPLEJIDAD_CRITICA: lista única, fuente de verdad.
  - detectar_complejidad_critica(): devuelve True/False + motivos.

Se usa desde:
  - app.services.glosa_service (R-CEREBRO #5, refinar_dictamen,
    auto-crítica refinamiento).
  - app.services.ia_router (clasificar_complejidad — para que el QG
    también enrute estos casos a Anthropic).
  - app.services.multi_codigo (_generar_seccion_codigo — cada código
    adicional re-evalúa la complejidad).

UMBRALES (idénticos a R-CEREBRO #5, + ronda 32):
  - valor ≥ $50M → COMPLEJO
  - valor ≥ $10M (solo, sin más señales) → COMPLEJO (ronda 32,
    ajustable con ROUTING_VALOR_SOLO_MIN)
  - 2+ PDFs Y valor ≥ $5M → COMPLEJO
  - 3+ códigos de glosa → COMPLEJO
  - texto > 4000 chars → COMPLEJO
  - palabra-clave crítica (Cart-T, Norwood, Epicel, hemofilia,
    Zolgensma, tutela, recobro, evento adverso, etc.) → COMPLEJO

Cualquier condición que se cumpla → escalación a Claude. Caso simple
(ninguna condición) → respeta primary_ai (típicamente Groq, gratis).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Palabras-clave que históricamente le revientan el dictamen a Llama 4
# Scout — oncología cara, neonatal grave, enfermedades raras, recobros,
# tutelas, evento adverso. Cuando aparecen en texto_glosa o contexto_pdf
# (uppercased), el motor escala a Anthropic incluso con primary_ai=groq.
#
# Esta lista debe mantenerse en SINCRONÍA con:
#   - REGLA 8 del system prompt (bloque clínico expandido en
#     glosa_ia_prompts.py — define los protocolos clínicos).
PALABRAS_CLAVE_COMPLEJIDAD_CRITICA: tuple[str, ...] = (
    # Oncología hematológica de alto costo
    "CART-T",
    "CAR-T",
    "TISAGENLECLEUCEL",
    "AXICABTAGENE",
    "CARTAGENA-T",
    # Cardiopatías congénitas neonatales
    "NORWOOD",
    "HIPOPLASIA VENTRICULAR",
    "HLHS",
    # Trasplantes
    "TRASPLANT",
    "ALOTRASPLANT",
    "AUTOTRASPLANT",
    # Hematología y enfermedades raras
    "HEMOFILIA",
    # Agentes de baña / bypassing (hemofilia con inhibidores) — la glosa a
    # veces no dice "hemofilia" sino el principio activo (caso real NUEVA EPS
    # 30-jun: "factor VII activado recombinante / eptacog alfa"). Sin estas
    # claves el caso —clínicamente complejo y de alto costo— se quedaba en
    # Groq en vez de escalar a Claude.
    "FACTOR VII",
    "EPTACOG",
    # Ronda 30: "INHIBIDOR" suelto escalaba cualquier glosa con IBP/IECA
    # ("inhibidor de bomba de protones"). Exige contexto hematológico.
    "INHIBIDOR DEL FACTOR",
    "INHIBIDORES DEL FACTOR",
    "FEIBA",
    "APCC",
    "GAUCHER",
    "POMPE",
    "CEREZYME",
    "FABRY",
    "MUCOPOLISACARIDOS",
    "MUCOPOLISACARIDOSIS",
    # Dispositivos quemados / dermatología
    "EPICEL",
    "ELIZARIA",
    # Terapias génicas / huérfanas
    "ATALUREN",
    "NUSINERSEN",
    "ZOLGENSMA",
    "ONASEMNOGENE",
    "DUCHENNE",
    "AME",
    "ATROFIA MUSCULAR ESPINAL",
    # Tutelas y recobros
    "TUTELA",
    "RECOBRO",
    "SENTENCIA DE TUTELA",
    "FALLO DE TUTELA",
    # Eventos adversos prevenibles (defensa difícil)
    "EVENTO ADVERSO",
    "PREVENIBLE",
    "MUERTE MATERNA",
    "DAÑO IATROG",
    "DAÑO IATROGENICO",
    "DAÑO IATROGÉNICO",
    "ENFERMEDAD HUÉRFANA",
    "ENFERMEDAD HUERFANA",
    "ENFERMEDADES HUÉRFANAS",
    "ENFERMEDADES HUERFANAS",
    # Vacunas y biológicos complejos
    "VPH-RECOMB",
    # Salud mental forzada / refractaria
    "PSIQUIATRIC REFRACTAR",
    "ESQUIZOFRENIA REFRACTARIA",
    "TMS",
    # Pediátrico de alta complejidad
    "IMPLANTE COCLEAR",
    "ESTIMULADOR CEREBRAL",
    "DBS",
    "DEEP BRAIN STIMULATION",
    # Cirugía robótica de alto costo
    "DA VINCI",
    "CIRUGIA ROBOTIC",
    "CIRUGÍA ROBÓTIC",
    # EPS intervenidas o en liquidación
    "EN LIQUIDACI",
    "EPS INTERVENIDA",
    "AGENTE LIQUIDADORA",
    "MEDIMAS EPS-S",
    "MEDIMÁS EPS-S",
    # Cuidados paliativos / muerte digna
    "MUERTE DIGNA",
    "CUIDADOS PALIATIVOS",
    "SEDACION PALIATIV",
    "SEDACIÓN PALIATIV",
    # Cáncer pediátrico
    "CANCER INFANTIL",
    "CÁNCER INFANTIL",
    "ONCOLOGIA PEDIATRIC",
    "ONCOLOGÍA PEDIÁTRIC",
)


# Ronda 32 (22-jul-2026): umbral de escalación por VALOR SOLO (sin otras
# señales). Los 4 casos de prueba del 22-jul mostraron glosas de $16.8M y
# $18.6M respondidas por Groq (texto pegado, sin PDFs → la regla de $5M+2PDFs
# no aplicaba y $50M quedaba lejos). Un dictamen de >$10M perdido por un
# modelo débil cuesta muchísimo más que la llamada a Claude.
# Ajustable sin redeploy: ROUTING_VALOR_SOLO_MIN (pesos, entero).
_UMBRAL_VALOR_SOLO_DEFAULT = 10_000_000


def _umbral_valor_solo() -> int:
    """Umbral de escalación por valor sin otras señales (env-ajustable)."""
    import os

    raw = (os.getenv("ROUTING_VALOR_SOLO_MIN", "") or "").strip()
    try:
        v = int(raw)
        return v if v > 0 else _UMBRAL_VALOR_SOLO_DEFAULT
    except (TypeError, ValueError):
        return _UMBRAL_VALOR_SOLO_DEFAULT


@dataclass
class ResultadoComplejidad:
    """Resultado del detector de complejidad crítica.

    es_complejo: True cuando el motor DEBE escalar a Anthropic.
    motivos: lista de strings legibles para logging y badges del panel.
    """

    es_complejo: bool
    motivos: list[str]


def detectar_complejidad_critica(
    *,
    valor: int | float | None = None,
    num_pdfs: int = 0,
    num_codigos: int = 0,
    texto_glosa: str = "",
    contexto_pdf: str = "",
    longitud_max_busqueda: int = 50000,
) -> ResultadoComplejidad:
    """Decide si el caso es de COMPLEJIDAD CRÍTICA → escalar a Anthropic.

    Args:
      valor: valor objetado de la glosa en pesos (int o float). 0/None
        no dispara solo.
      num_pdfs: cantidad de documentos PDF adjuntos (contexto multimodal).
      num_codigos: cantidad de códigos de glosa detectados.
      texto_glosa: texto crudo de la glosa de la EPS.
      contexto_pdf: texto extraído de los PDFs soporte.
      longitud_max_busqueda: cap para la concatenación texto_glosa +
        contexto_pdf antes de buscar palabras-clave (evita gastar tiempo
        en historiales clínicos gigantes).

    Returns:
      ResultadoComplejidad con es_complejo bool + motivos legibles.

    Cualquier condición individual basta para tipificar COMPLEJO:
      • valor ≥ $50.000.000
      • valor ≥ $10.000.000 solo (ronda 32 — ROUTING_VALOR_SOLO_MIN)
      • 2+ PDFs Y valor ≥ $5.000.000
      • 3+ códigos de glosa
      • texto_glosa > 4000 chars
      • cualquier palabra-clave crítica de PALABRAS_CLAVE_COMPLEJIDAD_CRITICA
    """
    motivos: list[str] = []

    valor_num = 0
    if valor is not None:
        try:
            valor_num = int(valor)
        except (TypeError, ValueError):
            valor_num = 0

    if valor_num >= 50_000_000:
        motivos.append(f"valor=${valor_num:,}")
    elif valor_num >= _umbral_valor_solo():
        # Ronda 32: alto valor escala SOLO, aunque no haya PDFs ni otras
        # señales — evidencia: casos de $16.8M/$18.6M respondidos por Groq.
        motivos.append(f"valor-alto=${valor_num:,}")

    if num_pdfs >= 2 and valor_num >= 5_000_000:
        motivos.append(f"pdfs={num_pdfs}+valor>=5M")

    if num_codigos >= 3:
        motivos.append(f"codigos={num_codigos}")

    longitud_texto = len(str(texto_glosa or ""))
    if longitud_texto > 4_000:
        motivos.append(f"texto={longitud_texto}c")

    # Busca palabras-clave críticas en (texto_glosa + contexto_pdf).
    texto_upper = (f"{texto_glosa or ''} {contexto_pdf or ''}"[:longitud_max_busqueda]).upper()
    palabra_encontrada: str | None = None
    for kw in PALABRAS_CLAVE_COMPLEJIDAD_CRITICA:
        # Ronda 27 (2-jul-2026): las keywords CORTAS exigen frontera de
        # palabra — "AME" (atrofia muscular espinal) matcheaba dentro de
        # "PREVIAMENTE"/"ADECUADAMENTE" y escalaba falsos positivos.
        if len(kw) <= 4:
            if re.search(rf"(?<![A-ZÁÉÍÓÚÑ0-9]){re.escape(kw)}(?![A-ZÁÉÍÓÚÑ0-9])", texto_upper):
                palabra_encontrada = kw
                break
        elif kw in texto_upper:
            palabra_encontrada = kw
            break
    if palabra_encontrada:
        motivos.append(f"palabra-clave-critica:{palabra_encontrada}")

    return ResultadoComplejidad(es_complejo=bool(motivos), motivos=motivos)


def multimodal_auto_activado(es_complejo: bool, modelo_override: str | None) -> bool:
    """Fase 2 Soportes (jul-2026): ¿auto-activar la lectura PDF nativa?

    Envía los PDFs binarios a Claude SOLO cuando el caso YA se enruta a un
    Claude "grande" (complejidad crítica u Opus por valor+multi-PDF). Los
    casos simples que van a Groq/Haiku siguen con el texto OCR — así el
    multimodal queda "ON por defecto" donde importa, sin convertir cada
    glosa con PDF en una llamada cara (la trampa que el usuario vetó).

    Apagable sin redeploy: GLOSA_MULTIMODAL_AUTO=0.
    """
    import os

    if os.getenv("GLOSA_MULTIMODAL_AUTO", "1").strip().lower() in ("0", "false", "no"):
        return False
    return bool(es_complejo or (modelo_override or "").startswith("claude-opus"))
