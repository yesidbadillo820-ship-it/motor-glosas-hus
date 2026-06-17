import os
import re
import hashlib
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from cachetools import TTLCache
from fastapi import HTTPException
from groq import AsyncGroq
from app.models.schemas import GlosaInput, GlosaResult
from app.core.logging_utils import logger
from app.services.glosa_ia_prompts import get_system_prompt, build_user_prompt

_CACHE_IA: TTLCache = TTLCache(maxsize=500, ttl=3600)


# ─── R54 P3: tarifas Anthropic (USD por millón de tokens) ───────────────
# Fuente: https://docs.anthropic.com/en/docs/about-claude/pricing
# Se actualizan manualmente cuando Anthropic cambia precios.
# Cache READ es 10% del precio de input normal (oferta estándar Anthropic).
# Cache WRITE 5min: 1.25× input. WRITE 1h (extended-cache-ttl): 2× input.
_TARIFAS_ANTHROPIC_USD_POR_MTOK = {
    # Familia Sonnet 4.x
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-7": {"input": 3.0, "output": 15.0},
    # Familia Opus 4.x
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    # Familia Haiku
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    # Default conservador
    "_default": {"input": 3.0, "output": 15.0},
}


def _calcular_costo_anthropic_usd(usage: dict, modelo: str) -> float:
    """Estima el costo USD de una llamada a Claude a partir del 'usage'.

    Considera:
      - input_tokens (precio normal)
      - cache_creation_input_tokens (con TTL=1h, 2× del precio input)
      - cache_read_input_tokens (10% del precio input)
      - output_tokens (precio output)
    """
    if not isinstance(usage, dict):
        return 0.0
    tarifas = _TARIFAS_ANTHROPIC_USD_POR_MTOK.get(
        modelo,
        _TARIFAS_ANTHROPIC_USD_POR_MTOK["_default"],
    )
    p_in = tarifas["input"]
    p_out = tarifas["output"]
    inp = usage.get("input_tokens", 0) or 0
    cwrite = usage.get("cache_creation_input_tokens", 0) or 0
    cread = usage.get("cache_read_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    costo = (
        (inp * p_in) + (cwrite * p_in * 2.0) + (cread * p_in * 0.1) + (out * p_out)
    ) / 1_000_000.0
    return round(costo, 6)


def _log_metricas_anthropic(usage: dict, modelo: str, latencia_ms: int) -> None:
    """Loggea SIEMPRE las métricas de un call a Anthropic en formato
    estructurado y parseable. Permite agregaciones desde Sentry / Loki.

    Formato:
      [ANTHROPIC-CALL] model=X latency_ms=Y in=Yt cache_w=Yt cache_r=Yt
                       out=Yt cost_usd=$0.012345 cache_hit_pct=NN.N
    """
    if not isinstance(usage, dict):
        return
    inp = usage.get("input_tokens", 0) or 0
    cwrite = usage.get("cache_creation_input_tokens", 0) or 0
    cread = usage.get("cache_read_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    total_in = inp + cwrite + cread
    cache_hit_pct = (cread / total_in * 100.0) if total_in else 0.0
    costo = _calcular_costo_anthropic_usd(usage, modelo)
    logger.info(
        f"[ANTHROPIC-CALL] model={modelo} latency_ms={latencia_ms} "
        f"in={inp}t cache_w={cwrite}t cache_r={cread}t out={out}t "
        f"cost_usd=${costo:.6f} cache_hit_pct={cache_hit_pct:.1f}"
    )
    # R55 P2 + R56 P1: persistir en ai_calls + atribución a usuario/glosa
    # vía ContextVars (sin acoplar firma del helper a la cadena de llamadas).
    # Try/except defensivo: un fallo de BD jamás debe romper la respuesta
    # IA — la métrica es secundaria al producto.
    try:
        from app.core.logging_utils import glosa_id_var, user_email_var
        from app.database import SessionLocal
        from app.models.db import AICallRecord

        db = SessionLocal()
        try:
            db.add(
                AICallRecord(
                    proveedor="anthropic",
                    modelo=modelo,
                    latency_ms=int(latencia_ms or 0),
                    input_tokens=inp,
                    cache_creation_input_tokens=cwrite,
                    cache_read_input_tokens=cread,
                    output_tokens=out,
                    cost_usd=costo,
                    user_email=(user_email_var.get() or None),
                    glosa_id=glosa_id_var.get(),
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[ANTHROPIC-CALL] no se pudo persistir métrica: {e}")


_CACHE_TTL = 3600
# Lock para evitar races cuando N requests concurrentes tocan la misma clave.
# TTLCache NO es thread-safe por default; con 10 usuarios paralelos escribiendo
# la misma tupla (respuesta, modelo) dos threads pueden corromper el dict.
_CACHE_IA_LOCK = asyncio.Lock()
# Límite máximo de tamaño de respuesta IA persistida en BD (~500KB).
# Protege contra respuestas gigantes que saturen el INSERT o consuman
# tiempo excesivo en networks lentos.
_CACHE_MAX_RESP_LEN = 500_000

_ERRORES_REINTENTABLES = frozenset(
    [
        "429",
        "rate",
        "limit",
        "timeout",
        "stream",
        "idle",
        "timed out",
        "connection",
        "503",
        "502",
        "reset",
        "eof",
    ]
)

# Presupuesto de tokens de salida por familia de modelo Groq (fix #9,
# 12-jun-2026). 3000 bastan para un argumento de 500-700 palabras en
# modelos NO razonadores (llama-3.3 / qwen3 con reasoning default). Los
# openai/gpt-oss-* son RAZONADORES: su chain-of-thought se descuenta del
# MISMO max_tokens, y con 3000 el razonamiento podía consumirlo todo →
# content vacío + finish_reason='length' → fallback a qwen innecesario
# (evidencia: [GROQ-FALLBACK] en prod 12-jun 19:37 UTC, llamada de
# auto-crítica). Mínimo 8000 para gpt-oss; el max() conserva el mayor si
# algún día se sube el presupuesto base por encima de ese piso.
_GROQ_MAX_TOKENS = 3000
_GROQ_MAX_TOKENS_GPT_OSS = max(_GROQ_MAX_TOKENS, 8000)

# Capability cache del SDK Groq (ronda 5, 16-jun-2026). El SDK instalado
# en producción NO acepta `reasoning_effort` como kwarg (TypeError del
# cliente, ni siquiera llega a la API). La ronda 4 introdujo el retry
# sin el parámetro — pero cada llamada repetía el TypeError porque la
# bandera era LOCAL a la función. Esta variable de proceso recuerda el
# fallo y omite el kwarg desde la primera llamada en adelante. Ahorro:
# ~8s por dictamen (logs Fly 18:01-18:03 UTC).
_GROQ_SDK_SOPORTA_REASONING_EFFORT: bool = True

# Versión del cache de IA (ronda 5, 16-jun-2026). Bumpear cuando cambien
# el system prompt, redes finales (descomillar/contratos/CUPS/EPS/
# fabricaciones), o sanitizadores (CoT leak / placeholders) — invalida
# todos los cachés viejos. El caso 8 de la ronda 3 vino del caché DB con
# etiqueta `groq/qwen/qwen3-32b` aunque los fixes ya estaban desplegados,
# porque la clave SHA256 no incluía señal de versión.
_PROMPT_CACHE_VERSION = "r10-20260617"

FERIADOS_CO = [
    # 2025
    "2025-01-01",
    "2025-01-06",
    "2025-03-24",
    "2025-04-17",
    "2025-04-18",
    "2025-05-01",
    "2025-06-02",
    "2025-06-23",
    "2025-06-30",
    "2025-07-20",
    "2025-08-07",
    "2025-08-18",
    "2025-10-13",
    "2025-11-03",
    "2025-11-17",
    "2025-12-08",
    "2025-12-25",
    # 2026
    "2026-01-01",
    "2026-01-12",
    "2026-03-23",
    "2026-04-02",
    "2026-04-03",
    "2026-05-01",
    "2026-05-18",
    "2026-06-08",
    "2026-06-15",
    "2026-06-29",
    "2026-07-20",
    "2026-08-07",
    "2026-08-17",
    "2026-10-12",
    "2026-11-02",
    "2026-11-16",
    "2026-12-08",
    "2026-12-25",
    # 2027 (Ley 1393/2010 - puentes psicológicos automáticos)
    "2027-01-01",
    "2027-01-11",
    "2027-03-22",
    "2027-04-01",
    "2027-04-02",
    "2027-05-01",
    "2027-05-17",
    "2027-06-07",
    "2027-06-14",
    "2027-06-28",
    "2027-07-20",
    "2027-08-07",
    "2027-08-16",
    "2027-10-11",
    "2027-11-01",
    "2027-11-15",
    "2027-12-08",
    "2027-12-25",
    # 2028 (estimados - verificar publicado)
    "2028-01-01",
    "2028-01-10",
    "2028-03-20",
    "2028-04-13",
    "2028-04-14",
    "2028-05-01",
    "2028-05-15",
    "2028-06-05",
    "2028-06-12",
    "2028-06-26",
    "2028-07-20",
    "2028-08-07",
    "2028-08-14",
    "2028-10-09",
    "2028-10-30",
    "2028-11-06",
    "2028-11-13",
    "2028-12-08",
    "2028-12-25",
]

# PLAZO LEGAL: 20 días hábiles para que la EPS formule la glosa (Art. 57 Ley 1438/2011
# operacionalizado por Decreto 4747/2007 + Res. 3047/2008 + criterio institucional HUS).
# Las glosas extemporáneas son improcedentes, abusivas y no deben disminuir el pago a las IPS.
DIAS_HABILES_LIMITE_EXTEMPORANEA = 20

NORMATIVA_COLOMBIA = """
NORMATIVA APLICABLE:
- Ley 100 de 1993: Sistema de Seguridad Social Integral (Art. 168 - Urgencias)
- Ley 1438 de 2011: Reforma al Sistema de Salud (Artículo 57 - Trámite de glosas; plazos: 20 días EPS formular | 15 días IPS responder | 10 días EPS decidir)
- Ley 1751 de 2015: Ley Estatutaria de Salud (Derecho fundamental a la salud)
- Ley 1122 de 2007: Flujo de recursos entre EPS e IPS (Art. 13)
- Decreto 4747 de 2007: Regulaciones sobre glosas y devoluciones (Art. 20 - Conciliación)
- Decreto 780 de 2016: Decreto Único Reglamentario del Sector Salud
- Resolución 2175 de 2015: Procedimiento de conciliación de glosas médicas
- Resolución 3047 de 2008: Anexo Técnico 5 (Procedimiento glosas)
- Resolución 5269 de 2017: Plan de Beneficios en Salud
- Circular Externa 047 de 2025 (MinSalud): Manual Tarifario SOAT 2026 indexado a UVB
- UVB 2026: $12.110 (Resolución MinHacienda 31/12/2025). Fórmula: valor = Tarifa_UVB × $12.110 → centena más próxima
- Decreto 780 de 2016 (Anexo Técnico 1): regla de redondeo a centena + marco general
- Decreto 2423 de 1996: Manual tarifario SOAT histórico (base para servicios no incluidos en Circular 047)
- Resolución 054 de 2026 (ESE HUS): Tarifas propias del hospital (aplican cuando el contrato dice "TIPO TARIFA = PROPIAS")
- Código de Comercio: Artículo 871 (Principio de Buena Fe)
- Circular 030 de 2013: Subsanación de errores formales en facturación
- Resolución 1995 de 1999: Historia clínica como prueba plena
- Sentencia T-760 de 2008: Obligaciones de las EPS en prestación de servicios
- Sentencia T-1025 de 2002: Urgencias no requieren autorización previa
- Sentencia T-478 de 1995: Autonomía médica como derecho fundamental
"""

ESTRATEGIAS_TIPO = {
    "TA_TARIFA": """ESTRATEGIA TARIFARIA PROFESIONAL:
- Verificar la tarifa liquidada vs tarifa contractual vigente (SOAT -15% o según convenio)
- Citar específicamente el contrato vigente y sus anexos tarifarios
- Invocar la Resolución Interna de Precios de la institución
- Principio de buena fe contractual (Art. 871 Código Comercio)
- Mencionar que la EPS no puede aplicar descuentos unilaterales sin sustento
- El IPC es un referente NO una obligación para la IPS
- Si hay incremento institucional debidamente aprobado, citar acto administrativo""",
    "SO_SOPORTES": "ESTRATEGIA SOPORTES: Historia clínica es plena prueba según Res. 1995/1999. Documentos cumplen norma. EPS tuvo 20 días hábiles para objetar (Art. 57 Ley 1438/2011).",
    "AU_AUTORIZACION": "ESTRATEGIA AUTORIZACIÓN: Atención por urgencia vital. No requiere autorización previa. Art. 168 Ley 100/1993 y Resolución 5269/2017.",
    "CO_COBERTURA": "ESTRATEGIA COBERTURA: Servicio dentro del Plan de Beneficios en Salud (Res. 5269/2017). EPS tiene obligación de pago. No hay exclusiones.",
    "CL_PERTINENCIA": "ESTRATEGIA PERTINENCIA: Autonomía médica protegida por Art. 17 Ley 1751/2015. Criterio del médico tratante prevalece. Historia clínica soporta la decisión.",
    "PE_PERTINENCIA": "ESTRATEGIA PERTINENCIA: Autonomía médica protegida por Art. 17 Ley 1751/2015. Criterio del médico tratante prevalece. Historia clínica soporta la decisión.",
    "FA_FACTURACION": "ESTRATEGIA FACTURACIÓN: Error formal no es causal de glosa (Circular 030/2013). Los errores formales son subsanables. La prestación del servicio genera obligación de pago.",
    "IN_INSUMOS": "ESTRATEGIA INSUMOS: Inherentes al acto médico. Se facturan al costo de adquisición más porcentaje administrativo pactado. Factura de compra disponible como soporte.",
    "ME_MEDICAMENTOS": "ESTRATEGIA MEDICAMENTOS: Dispensados bajo fórmula médica. Plan de Beneficios los incluye (Res. 5269/2017). No existe alternativa terapéutica equivalente.",
    "EXT_EXTEMPORANEA": "ESTRATEGIA EXTEMPORÁNEA: Glosa improcedente por extemporaneidad. Art. 57 Ley 1438/2011 + Decreto 4747/2007 establecen 20 días hábiles para formular glosas. EPS perdió el derecho a glosar. Estas glosas son abusivas y no pueden disminuir el pago a la IPS.",
}

CODIGOS_GLOSA = {
    "TA": "OBJECIÓN POR TARIFA",
    "SO": "OBJECIÓN POR SOPORTES",
    "AU": "OBJECIÓN POR AUTORIZACIÓN",
    "CO": "OBJECIÓN POR COBERTURA",
    "CL": "OBJECIÓN POR PERTINENCIA",
    "PE": "OBJECIÓN POR PERTINENCIA",
    "FA": "OBJECIÓN POR FACTURACIÓN",
    "IN": "OBJECIÓN POR INSUMOS",
    "ME": "OBJECIÓN POR MEDICAMENTOS",
    "SE": "OBJECIÓN SIN ESPECIFICACIÓN",
    "EX": "OBJECIÓN EXTEMPORÁNEA",
}

PLANTILLAS_CODIGO = {}


def obtener_plantilla_por_codigo(codigo: str) -> Optional[dict]:
    """Obtiene la plantilla específica para un código de glosa."""
    return PLANTILLAS_CODIGO.get(codigo.upper())


_ABREV_A_NOMBRE = {
    "TA": "TARIFAS",
    "SO": "SOPORTES",
    "AU": "AUTORIZACIÓN",
    "CO": "COBERTURA",
    "CL": "PERTINENCIA CLÍNICA",
    "PE": "PERTINENCIA CLÍNICA",
    "FA": "FACTURACIÓN",
    "IN": "INSUMOS",
    "ME": "MEDICAMENTOS",
}


def _expandir_abreviaturas_tipo(texto: str) -> str:
    """Reemplaza abreviaturas de tipo (TA, SO, AU, CO, CL/PE, FA, IN, ME) por
    sus nombres completos cuando aparecen referidas al concepto de la glosa.

    Solo reemplaza cuando la abreviatura va precedida por palabras como
    'CONCEPTO DE', 'DEFENSA POR', 'POR' — para no alterar los códigos de
    glosa concretos (TA0801, SO0101, etc.).
    """
    if not texto:
        return texto
    for abrev, nombre in _ABREV_A_NOMBRE.items():
        # "CONCEPTO DE TA," "CONCEPTO DE TA." "CONCEPTO DE TA\n"
        texto = re.sub(
            rf"\bCONCEPTO\s+DE\s+{abrev}\b(?!\d)",
            f"CONCEPTO DE {nombre}",
            texto,
        )
        # "DEFENSA POR TA" / "GLOSA POR TA"
        texto = re.sub(
            rf"\bPOR\s+{abrev}\b(?!\d)",
            f"POR {nombre}",
            texto,
        )
        # "TIPO TA," "TIPO TA." al final de frase
        texto = re.sub(
            rf"\bTIPO\s+{abrev}\b(?!\d)",
            f"TIPO {nombre}",
            texto,
        )
    return texto


def _truncar_runaway(texto: str, max_repeticiones: int = 3) -> str:
    """Detecta loops degenerate de la IA (ej. "DEL X DEL X DEL X...") y
    trunca el texto en el punto donde comienza el bucle.

    Heurística: busca cualquier ngrama de 2-5 palabras que se repita más
    de max_repeticiones veces seguidas. Si lo encuentra, corta ahí.
    """
    if not texto or len(texto) < 200:
        return texto
    palabras = texto.split()
    if len(palabras) < 20:
        return texto

    for tam_ngrama in (2, 3, 4, 5):
        i = 0
        while i < len(palabras) - tam_ngrama * (max_repeticiones + 1):
            ngrama = palabras[i : i + tam_ngrama]
            # Contar repeticiones consecutivas
            repes = 1
            j = i + tam_ngrama
            while j + tam_ngrama <= len(palabras) and palabras[j : j + tam_ngrama] == ngrama:
                repes += 1
                j += tam_ngrama
                if repes > max_repeticiones:
                    # ENCONTRAMOS LOOP — truncar en el inicio del bucle
                    truncado = " ".join(palabras[: i + tam_ngrama])
                    # Agregar cierre limpio
                    if not truncado.rstrip().endswith((".", " ")):
                        truncado += "."
                    truncado += (
                        " [TEXTO TRUNCADO POR SISTEMA: LA IA ENTRÓ EN BUCLE — REVISAR Y RE-GENERAR]"
                    )
                    return truncado
            i += 1
    return texto


def _dedup_oraciones_largas(texto: str, min_palabras: int = 15) -> str:
    """Elimina repeticiones textuales largas dentro del dictamen.

    Auditoría 10-jun-2026 P2-6: Groq citó la cláusula primera completa
    (~60 palabras entre «») DOS veces en el mismo párrafo y nada lo
    atrapó — _truncar_runaway solo detecta n-gramas de 2-5 palabras
    repetidos >3 veces consecutivas (loops degenerados), no párrafos
    duplicados a distancia. Dos redes:

      1. Oración repetida textualmente (>= min_palabras) → se descarta
         la repetición.
      2. CITA LARGA repetida (texto entre «» / comillas de >= 12
         palabras): los preámbulos suelen cambiar ("PORQUE..." vs
         "EN VIRTUD DE LO ANTERIOR...") así que la oración no es
         idéntica, pero la cita sí — se descarta la oración que re-cita.

    Solo toca contenido LARGO — las frases rituales cortas legítimas
    ("SE SOLICITA EL LEVANTAMIENTO...") no alcanzan el umbral.
    """
    if not texto or len(texto) < 300:
        return texto
    # Separar por fin de oración conservando el delimitador.
    partes = re.split(r"(?<=[.;])\s+", texto)
    if len(partes) < 3:
        return texto

    def _clave(s: str) -> str:
        s = re.sub(r"\s+", " ", s).strip().upper()
        return re.sub(r"[^\wÁÉÍÓÚÑ ]", "", s)

    pat_cita = re.compile(r"[«\"“]([^«»\"“”]{40,800})[»\"”]")
    vistas_oraciones: set[str] = set()
    vistas_citas: set[str] = set()
    resultado: list[str] = []
    for oracion in partes:
        clave_o = _clave(oracion)
        if len(clave_o.split()) >= min_palabras and clave_o in vistas_oraciones:
            continue  # oración repetida textual — descartar
        citas = [_clave(c) for c in pat_cita.findall(oracion)]
        citas_largas = [c for c in citas if len(c.split()) >= 12]
        if citas_largas and any(c in vistas_citas for c in citas_largas):
            continue  # re-cita la misma cláusula/norma larga — descartar
        if len(clave_o.split()) >= min_palabras:
            vistas_oraciones.add(clave_o)
        vistas_citas.update(citas_largas)
        resultado.append(oracion)
    return " ".join(resultado)


# ── Sanitizer chain-of-thought leakage (16-jun-2026, ronda 3 — bug nuevo) ──
# Evidencia: 7 dictámenes ENTREGADOS con texto del razonamiento interno del
# modelo en el cuerpo del dictamen:
#   "tags. Let me go through each section step by step, making sure all
#    corrections are applied without changing the legal substance."
#   "changes. Let me draft each part step by step, making sure each
#    correction is addressed. ... Alright, let's put it all together.
#    ```xml"
# Causa raíz: qwen3-32b (y a veces gpt-oss) emite razonamiento ANTES o
# EN LUGAR de las tags XML pedidas. Cuando el extractor de <argumento>
# cae al fallback (toma todo res_ia), el razonamiento crudo llega al
# dictamen. NO toca texto en español del dictamen ni citas legítimas —
# los marcadores son frases en inglés que el modelo "habla consigo mismo".
# Marcadores en inglés que el razonador emite "hablándose a sí mismo". El
# dictamen es en español → frases como "Let me", "Let's", "Alright, let's"
# no aparecen legítimamente. Detectamos en los primeros ~120 chars de cada
# línea para no descartar líneas largas con contenido válido al final.
_PAT_COT_MARKERS = re.compile(
    r"""(?ix)
    (?:^|[\s.;:,—\-])
    (?:
        let\s+me\b
       |let'?s\b
       |alright,?\s+let'?s\b
       |alright,?\s+let\s+me\b
       |okay,?\s+let'?s\b
       |okay,?\s+let\s+me\b
       |now,?\s+let'?s\b
       |now,?\s+let\s+me\b
       |i'?ll\s+(?:go|draft|write|put|make|start|review|check|use|need)\b
       |i\s+will\b
       |make\s+sure\b
       |check\s+(?:the|for)\b
       |first,?\s+let\b
    )
    """
)
_PAT_FENCE_MARKDOWN = re.compile(r"```(?:xml|json|python|text|html|markdown)?\s*\n?", re.IGNORECASE)
_PAT_TAG_SUELTO_LINEA = re.compile(
    r"^\s*(?:tags?\.?|</?(?:answer|response)>|<answer>|<response>)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
# "tags." al inicio de línea cuando le sigue contenido (frase completa)
_PAT_TAGS_PREFIJO = re.compile(r"(?im)^\s*tags?\.\s+")


def _limpiar_chain_of_thought(texto: str) -> str:
    """Sanitiza el output de la IA quitando rastros de chain-of-thought.

    Razonadores como qwen3/gpt-oss a veces emiten razonamiento ANTES o EN
    LUGAR de las tags XML solicitadas. Cuando el extractor de <argumento>
    cae al fallback (toma todo res_ia), el razonamiento crudo llega al
    dictamen entregado. Esta función:
      (a) Elimina fences sueltos ```xml, ```json
      (b) Elimina tokens sueltos "tags.", "</answer>", "<response>"
      (c) Elimina líneas cuyo primer chunk (≤120 chars) contiene un marcador
          de razonamiento en inglés ("Let me", "I'll draft", "Make sure"…).
          Los dictámenes son en español; estos marcadores no aparecen
          legítimamente.

    NO toca texto en español del dictamen ni citas legítimas.
    """
    if not texto:
        return texto
    resultado = _PAT_FENCE_MARKDOWN.sub("", texto)
    # "tags." como prefijo de una frase → quitar solo el prefijo, no la línea
    resultado = _PAT_TAGS_PREFIJO.sub("", resultado)
    # Tokens sueltos en línea propia
    resultado = _PAT_TAG_SUELTO_LINEA.sub("", resultado)
    # Líneas con marcador CoT en los primeros 120 chars → drop completo
    lineas_limpias = []
    n_filtradas = 0
    for linea in resultado.splitlines():
        if _PAT_COT_MARKERS.search(linea[:120]):
            n_filtradas += 1
            continue
        lineas_limpias.append(linea)
    resultado = "\n".join(lineas_limpias)
    resultado = re.sub(r"\n{3,}", "\n\n", resultado).strip()
    if n_filtradas:
        logger.warning(
            f"[COT-LEAK] {n_filtradas} línea(s) de chain-of-thought eliminadas "
            "del output de la IA antes de entrega final (red de la ronda 3)."
        )
    return resultado


# ── Red final: contratos de OTRA EPS en el dictamen (16-jun-2026, ronda 3) ──
# El check_contrato_de_otra_eps del QG ya regenera cuando dispara, pero el
# flujo legacy (QG OFF por default) lo deja pasar. Análoga determinística a
# _descomillar_citas_falsas: cada mención del número de contrato ajeno se
# sustituye por "el contrato vigente entre las partes" antes de entrega.
# ── Red final: nombres de EPS ajenos / inventados (ronda 5, 16-jun-2026) ──
# Evidencia caso 4 (COOSALUD): el dictamen escribió "interpuesta por la
# entidad Auditoría de la EPS SaludCo, respecto del servicio de
# hospitalización facturado por valor de cinco millones de pesos". La EPS
# era COOSALUD pero el modelo fabricó "SaludCo" y CAMBIÓ el valor. El
# bug es doble (EPS + valor) — esta red ataca SOLO el primero porque el
# segundo es un agregado del valor objetado por concepto. Conservadora:
# si el dictamen menciona una EPS conocida ≠ la del input, la sustituye
# por la EPS del input. Si menciona algo que parece nombre de EPS pero
# NO está en el catálogo, lo neutraliza a "la entidad pagadora".
_PAT_NOMBRE_EPS_GENERICA = re.compile(
    # "EPS X", "la EPS XYZ", "entidad ABC EPS" — capturamos solo el sintagma
    # COMPLETO, no fragmentos sueltos. Conservador: exige conector EPS.
    r"\b(?:LA\s+)?EPS\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ0-9.\- ]{2,30}?)(?=[,.\s]|\bEPS\b|$)",
    re.IGNORECASE,
)
_EPS_KNOWN_TOKENS = {
    "NUEVA",
    "FAMISANAR",
    "COOSALUD",
    "SANITAS",
    "COMPENSAR",
    "MUTUAL SER",
    "MUTUALSER",
    "SALUD TOTAL",
    "SALUDTOTAL",
    "SURA",
    "ECOOPSOS",
    "ECOOPSALUD",
    "EMSSANAR",
    "ASMET SALUD",
    "ASMETSALUD",
    "DMBUG",
    "DISPENSARIO",
    "FOMAG",
    "MAGISTERIO",
    "ARL",
    "SOAT",
}

# Ronda 10 (17-jun-2026) — palabras del DICCIONARIO en español que NO son
# nombre de EPS aunque sigan a "EPS" en una frase. Evidencia producción
# 17-jun (FAMISANAR HUS0000506597): la IA escribió "LAS EPS RECONOCER LOS
# SERVICIOS" — el regex matcheó "EPS RECONOCER", trató "RECONOCER" como
# nombre inventado y lo reemplazó por "la entidad pagadora", dejando la
# sintaxis rota "LAS la entidad pagadora RECONOCER". Stop-list excluye
# verbos/adverbios comunes que la IA puede dejar pegados a "EPS" tras
# elidir el sujeto plural.
_EPS_PALABRAS_NO_NOMBRE: frozenset[str] = frozenset(
    {
        # Verbos en infinitivo / conjugados
        "RECONOCER",
        "RECONOCERA",
        "RECONOCERÁ",
        "RECONOCERAN",
        "RECONOCERÁN",
        "RECONOZCAN",
        "RECONOZCA",
        "PAGAR",
        "PAGARA",
        "PAGARÁ",
        "PAGARAN",
        "PAGARÁN",
        "ESTABLECE",
        "ESTABLECEN",
        "ESTABLECEN",
        "ESTABLECER",
        "ESTABLECIO",
        "ESTABLECIÓ",
        "ESTABLECIDA",
        "ESTABLECIDAS",
        "ESTABLECIDO",
        "ESTABLECIDOS",
        "DEBE",
        "DEBEN",
        "DEBERA",
        "DEBERÁ",
        "DEBERAN",
        "DEBERÁN",
        "DEBERIA",
        "DEBERÍA",
        "DEBIERA",
        "DEBIERAN",
        "APLICA",
        "APLICAN",
        "APLICAR",
        "APLICARA",
        "APLICARÁ",
        "APLICARAN",
        "APLICANDO",
        "APLICÓ",
        "APLICO",
        "PRETENDE",
        "PRETENDEN",
        "PRETENDIO",
        "PRETENDIÓ",
        "ARGUMENTA",
        "ARGUMENTAN",
        "ARGUMENTÓ",
        "ARGUMENTO",
        "OBJETA",
        "OBJETAN",
        "OBJETÓ",
        "OBJETO",
        "NIEGA",
        "NIEGAN",
        "NEGÓ",
        "NEGO",
        "AFIRMA",
        "AFIRMAN",
        "AFIRMÓ",
        "AFIRMO",
        "ALEGA",
        "ALEGAN",
        "ALEGÓ",
        "ALEGO",
        "SOSTIENE",
        "SOSTIENEN",
        "SOSTUVO",
        "INCURRE",
        "INCURREN",
        "INCURRIÓ",
        "INCURRIO",
        "TIENE",
        "TIENEN",
        "TUVO",
        "VULNERA",
        "VULNERAN",
        "OMITE",
        "OMITEN",
        "DESCONOCE",
        "DESCONOCEN",
        # Adjetivos / participios / adverbios sueltos
        "VIGENTE",
        "VIGENTES",
        "RESPONSABLE",
        "RESPONSABLES",
        "LEGALMENTE",
        "UNILATERALMENTE",
        "EXPRESAMENTE",
        "OBLIGADAS",
        "OBLIGADA",
        "OBLIGADOS",
        "OBLIGADO",
        # Conectores y demás
        "PERO",
        "MAS",
        "AUN",
        "AÚN",
        "SIN",
        "PARA",
        "POR",
        "CON",
        "DE",
        "QUE",
        "QUIEN",
        "QUIENES",
        "CUYO",
        "CUYA",
        "CUYOS",
        "CUYAS",
        # Pronombres
        "ELLA",
        "ELLAS",
        "ELLOS",
        "TODAS",
        "TODOS",
        "AMBAS",
        "AMBOS",
        # Conceptos del dominio que no son EPS
        "CONTRIBUTIVO",
        "SUBSIDIADO",
        "PARTICULAR",
    }
)


def _neutralizar_eps_inventada(texto: str, eps: str) -> str:
    """Sustituye nombres de EPS distintos al del input por "la entidad pagadora".

    Caso 4 evidencia: con EPS=COOSALUD el dictamen inventó "EPS SaludCo".
    Estrategia:
      • Detecta menciones "EPS <NOMBRE>" en el dictamen.
      • Si <NOMBRE> NO coincide con la EPS del input ni con ninguna EPS
        conocida del catálogo, lo neutraliza a "la entidad pagadora".
      • Si <NOMBRE> ES una EPS conocida distinta de la del input → también
        neutraliza (caso de mezcla de EPS reales).
      • Si la EPS del input es "OTRA / SIN DEFINIR", no hace nada (no hay
        referencia para validar).
    """
    if not texto:
        return texto
    eps_up = (eps or "").upper().strip()
    if not eps_up or eps_up in {"OTRA", "OTRA / SIN DEFINIR", "SIN DEFINIR"}:
        return texto
    # Token raíz de la EPS del input (primera palabra significativa).
    raiz_input = eps_up.split()[0].strip(".,")

    n_sub = 0

    def _sub(m: "re.Match[str]") -> str:
        nonlocal n_sub
        nombre = (m.group(1) or "").strip(" .,;:").upper()
        if not nombre:
            return m.group(0)
        # Token raíz de la EPS mencionada.
        raiz_mencion = nombre.split()[0].strip(".,") if nombre.split() else ""
        if not raiz_mencion:
            return m.group(0)
        # Ronda 10 — el "nombre" es realmente una palabra común del español
        # (verbo, adverbio, conector) que la IA dejó pegada a "EPS" al
        # elidir el sujeto. Ejemplo prod 17-jun: "LAS EPS RECONOCER LOS
        # SERVICIOS" → no sustituir, dejar el texto como está.
        if raiz_mencion in _EPS_PALABRAS_NO_NOMBRE:
            return m.group(0)
        # Coincide con la EPS del input → respetar.
        if raiz_mencion == raiz_input or raiz_input in nombre or raiz_mencion in eps_up:
            return m.group(0)
        # Es una EPS conocida del catálogo, pero DISTINTA de la del input →
        # contraindicación.
        es_conocida_otra = raiz_mencion in _EPS_KNOWN_TOKENS
        # Si no es conocida y no coincide → es probablemente inventada
        # (e.g. "SaludCo"). Si es conocida pero ≠ input → contrato cruzado.
        if not es_conocida_otra and len(raiz_mencion) >= 3:
            n_sub += 1
            return "la entidad pagadora"
        if es_conocida_otra:
            n_sub += 1
            return "la entidad pagadora"
        return m.group(0)

    resultado = _PAT_NOMBRE_EPS_GENERICA.sub(_sub, texto)
    if n_sub:
        logger.warning(
            f"[EPS-INVENTADA] {n_sub} mención(es) de EPS distinta del input "
            f"(eps_input={eps_up}) neutralizadas en el dictamen final."
        )
    return resultado


# ── Red final: frases absurdas sin valor legal (ronda 6, 16-jun-2026 — fix J) ──
# Evidencia caso 10 PPL: "Conforme a la cláusula preventiva del contrato,
# numeral 12, CUALQUIER INTENTO DE REBATIR ESTA SOLICITUD SERÁ CONSIDERADO
# IMPROCEDENTE." Y caso 12 Compensar: "Esta respuesta es definitiva y NO
# ADMITE REBATIMIENTO ALGUNO." Son frases arrogantes que la IA inventa
# para "cerrar" el dictamen — pero NO tienen valor legal (la EPS siempre
# puede ratificar). Las eliminamos antes de entregar.
_PATRONES_FRASES_ABSURDAS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"[\"“‘'«»]?[^\"“”‘’'«»\n\.]{0,40}(?:NO\s+ADMITE\s+REBATIMIENTO|"
        r"NO\s+ADMITE\s+CONTROVERSIA|"
        r"NO\s+SE\s+ADMITE\s+(?:NINGUNA\s+)?(?:CONTROVERSIA|REBATIMIENTO|RECURSO|IMPUGNACI[ÓO]N))"
        r"[^\"“”‘’'«»\n\.]{0,40}[\"“”‘’'«»]?[\.\s]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:CUALQUIER\s+INTENTO\s+DE\s+REBATIR|"
        r"TODO\s+INTENTO\s+DE\s+REBATIR|"
        r"CUALQUIER\s+OBJECI[ÓO]N\s+ADICIONAL|"
        r"CUALQUIER\s+INTENTO\s+DE\s+IMPUGN(?:ACI[ÓO]N|AR))"
        r"[^\.\n]{0,80}(?:IMPROCEDENTE|INADMISIBLE|RECHAZADA?)[\.\s]*",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:ESTA\s+RESPUESTA|EL\s+PRESENTE\s+DICTAMEN|EL\s+PRESENTE\s+ESCRITO)"
        r"\s+(?:ES\s+|SER[ÁA]\s+)?(?:DEFINITIV[OA]|INAPELABLE|FINAL)"
        r"(?:\s+(?:E\s+)?INAPELABLE|\s+Y\s+(?:NO\s+ADMITE|VINCULANTE)|"
        r"\s+Y\s+NO\s+SUSCEPTIBLE\s+DE)?"
        r"[^\.\n]{0,80}[\.\s]*",
        re.IGNORECASE,
    ),
    # Ronda 7 (16-jun-2026 — fix N): "no susceptible de nueva impugnación"
    # (caso 9 FOMAG ronda 6 — cláusula "ANTI-REBATIMIENTO" inventada).
    re.compile(
        r"(?:[^\"“”‘’'«»\n\.]{0,60}"
        r"NO\s+SUSCEPTIBLE\s+DE\s+(?:NUEVA\s+|MAYOR\s+|ULTERIOR\s+)?(?:IMPUGNACI[ÓO]N|OBJECI[ÓO]N|"
        r"REVISI[ÓO]N|RECURSO|CONTROVERSIA)"
        r"[^\.\n]{0,80})[\.\s]*",
        re.IGNORECASE,
    ),
    # "CLÁUSULA X — ANTI-REBATIMIENTO" inventada
    re.compile(
        r"CL[ÁA]USULA\s+\d{1,3}\s*[-—–]\s*ANTI[-‐\s]?REBATIMIENTO[^\.\n]{0,160}[\.\s]*",
        re.IGNORECASE,
    ),
)


def _neutralizar_frases_absurdas(texto: str) -> str:
    """Elimina muletillas arrogantes sin valor legal del dictamen."""
    if not texto:
        return texto
    resultado = texto
    n_total = 0
    for pat in _PATRONES_FRASES_ABSURDAS:
        nuevo, n = pat.subn(" ", resultado)
        if n:
            n_total += n
            resultado = nuevo
    if n_total:
        # Limpieza de dobles espacios y "  ." que queden de la eliminación.
        resultado = re.sub(r"\s{2,}", " ", resultado)
        resultado = re.sub(r"\s+([\.,;])", r"\1", resultado)
        logger.warning(
            f"[FRASE-ABSURDA] {n_total} frase(s) sin valor legal "
            "neutralizadas en el dictamen final ('no admite rebatimiento', "
            "'cualquier intento improcedente', 'respuesta definitiva')."
        )
    return resultado


# ── Red final: código de glosa coherente (ronda 6, 16-jun-2026 — fix I) ──
# Evidencia caso 9 (FOMAG, DE0101) → "CÓDIGO N/A" en cabecera; caso 12
# (Compensar, CL0801) → "CÓDIGO 12345" inventado; caso 13 (NUEVA EPS,
# TA0201) → "CÓDIGO 118800" (número de factura). Si el dictamen menciona
# explícitamente un "código" distinto del código del input, sustituimos
# por el real o degradamos a "el código de la glosa aplicada".
_PAT_CODIGO_EN_DICTAMEN = re.compile(
    # Ronda 7 (16-jun-2026 — fix M): añadidos códigos cortos (1-3 dígitos
    # puros, e.g. "CÓDIGO 001", "CÓDIGO 12345"). Evidencia caso 12: el
    # dictamen escribió "SOBRE EL CÓDIGO 001" y el regex anterior pedía
    # ≥4 dígitos. Ahora captura también 1-3 dígitos puros.
    r"(?:SOBRE\s+EL\s+|CON\s+|DE\s+LA\s+GLOSA\s+|GLOSA\s+)?C[ÓO]DIGO\s+"
    r"([A-Z]{2}\d{4}|\d{1,8}|N/A|N\.A\.)",
    re.IGNORECASE,
)


def _normalizar_codigo_dictamen(
    texto: str,
    codigo_real: str,
    codigos_validos: "Optional[list[str]]" = None,
) -> str:
    """Si el dictamen menciona un código distinto del real, corrige.

    `codigo_real`: el código del input (ej. 'CL0801', 'AU0301'). Si está
    vacío o es 'N/A', no se hace nada (no hay referencia para validar).

    `codigos_validos`: lista de códigos adicionales que TAMBIÉN se aceptan
    sin corregir (multi-código: dictamen agrupa varios códigos con
    secciones por cada uno). Si está vacía o es None, sólo `codigo_real`
    se acepta. Conservador por defecto.
    """
    if not texto or not codigo_real or codigo_real.strip().upper() in {"N/A", ""}:
        return texto
    codigo_real_up = codigo_real.strip().upper()
    aceptados: set[str] = {codigo_real_up}
    for c in codigos_validos or []:
        if c:
            aceptados.add(c.strip().upper())
    n_sub = 0

    def _sub(m: "re.Match[str]") -> str:
        nonlocal n_sub
        cod_visto = m.group(1).strip().upper()
        # Si el visto está en la lista de aceptados (principal + secciones
        # multi-código), respetar.
        if cod_visto in aceptados:
            return m.group(0)
        # Si es 'N/A' o número puro, claramente no es código → corregir
        # al real (principal).
        if cod_visto in {"N/A", "N.A."} or cod_visto.isdigit():
            n_sub += 1
            return m.group(0).replace(m.group(1), codigo_real_up)
        # Si es otro código alfanumérico válido distinto del real y NO está
        # en aceptados → corregir.
        if re.fullmatch(r"[A-Z]{2}\d{4}", cod_visto) and cod_visto not in aceptados:
            n_sub += 1
            return m.group(0).replace(m.group(1), codigo_real_up)
        return m.group(0)

    resultado = _PAT_CODIGO_EN_DICTAMEN.sub(_sub, texto)
    if n_sub:
        logger.warning(
            f"[CODIGO-INCOHERENTE] {n_sub} mención(es) de código distinto del "
            f"input ({codigo_real_up}) corregidas en el dictamen final."
        )
    return resultado


# ── Red final: cierre de truncamiento (ronda 7, 16-jun-2026 — fix S) ──
# Evidencia caso 13 NUEVA EPS: el dictamen terminó con "(ART. 2284/2023»."
# — paréntesis sin cerrar y comilla suelta. Al modelo se le acabó el
# presupuesto y dejó la frase a medias. Detectamos los cierres rotos y
# los limpiamos sin inventar texto: si la última frase del argumento
# termina en " QUE" o " EN" o un paréntesis abierto, cortamos hasta el
# último punto/`.`/cierre limpio anterior y añadimos puntuación neutra.
_PAT_TRUNCAMIENTO_FINAL = re.compile(
    # Captura los últimos 200 chars del texto sin punto final (frase
    # incompleta). Conservador: solo si NO termina ya con cierre limpio.
    r"([^\.\!\?\»\)]*\([^\)]{0,200})\s*[\»\"\'\.]*\s*$",
    re.IGNORECASE,
)


def _cerrar_truncamiento(texto: str) -> str:
    """Si el final del texto está truncado (paréntesis sin cerrar, comilla
    suelta tras una frase incompleta), corta hasta el último cierre limpio
    y añade puntuación neutra. Conservador: solo cuando hay paréntesis
    sin cerrar o frase visiblemente incompleta."""
    if not texto:
        return texto
    # Caso 13: "...DECRETO 780/2016 ART. 2284/2023». ADEMÁS..." sin cerrar
    # paréntesis. Detectar paréntesis abiertos sin cerrar en los últimos
    # 400 chars.
    cola = texto[-400:]
    abre = cola.count("(")
    cierra = cola.count(")")
    if abre > cierra:
        # Cortar hasta el último punto antes del paréntesis huérfano.
        ult_par_abre = texto.rfind("(")
        if ult_par_abre > 0:
            ult_punto = texto.rfind(".", 0, ult_par_abre)
            if ult_punto > 0 and (len(texto) - ult_punto) < 400:
                resultado = texto[: ult_punto + 1] + " Se solicita el levantamiento de la glosa."
                logger.warning(
                    "[TRUNCAMIENTO] Dictamen truncado mid-sentence (paréntesis "
                    "sin cerrar) — cortado al último punto y cerrado con "
                    "petición estándar."
                )
                return resultado
    # Caso: termina con "QUE", "EN", ":", "—", coma sin texto detrás
    # (case-insensitive). Ronda 7 fix S.
    cola_fin = texto.rstrip().rstrip(".»\"'”„").rstrip()
    cola_fin_up = cola_fin.upper()
    if cola_fin_up.endswith(
        (" QUE", " EN", " DE", " A", " O", " Y", " LA", " EL", ":", "—", "-", "/")
    ):
        ult_punto = texto.rfind(".", 0, len(texto) - 5)
        if ult_punto > 0 and (len(texto) - ult_punto) < 200:
            resultado = texto[: ult_punto + 1] + " Se solicita el levantamiento de la glosa."
            logger.warning(
                "[TRUNCAMIENTO] Dictamen terminó con conector colgado — "
                "cortado al último punto y cerrado con petición estándar."
            )
            return resultado
    return texto


def _neutralizar_contratos_ajenos(texto: str, eps: str) -> str:
    """Elimina menciones a números de contrato que pertenecen a OTRA EPS.

    Evidencia ronda 3 (caso 5, DISPENSARIO MEDICO): el dictamen citó
    "cláusula tercera del contrato 440-DIGSA/DMBUG-2025" cuando ese
    contrato es del régimen militar (DMBUG), no de DISPENSARIO MEDICO.
    Citar contrato ajeno invalida el dictamen completo ante la EPS.
    """
    if not texto or not eps:
        return texto
    try:
        from app.services.glosa_ia_prompts import contratos_ajenos_citados
    except Exception:
        return texto
    ajenos = contratos_ajenos_citados(texto, eps)
    if not ajenos:
        return texto
    resultado = texto
    n_sub = 0
    for tok in ajenos:
        # El token viene en MAYÚSCULAS desde catalogo_contratos_eps(). Se
        # busca con palabras de contexto que la IA suele anteponer (CONTRATO,
        # ACTA, NÚMERO) para sustituir un sintagma natural, no un fragmento.
        pat = re.compile(
            r"(?:(?:CONTRATO|EL\s+CONTRATO)\s+(?:N[ÚU]MERO\s+)?)?" + re.escape(tok),
            re.IGNORECASE,
        )
        nuevo, n = pat.subn("el contrato vigente entre las partes", resultado)
        if n:
            resultado = nuevo
            n_sub += n
    if n_sub:
        logger.warning(
            f"[CONTRATO-AJENO] {n_sub} mención(es) de contrato de otra EPS "
            f"neutralizadas en el dictamen final (eps={eps}, ajenos={ajenos[:3]})."
        )
    return resultado


# ── Red final: "CUPS <fecha/factura>" en el dictamen (16-jun-2026, ronda 3) ──
# Evidencia caso 4 (COOSALUD): el texto traía "Verificar radicado 20260511 y
# soporte 4710-2026" → la IA escribió "código CUPS 20260511" (20260511 es
# yyyymmdd = 11/05/2026, no un código). El extractor de CUPS ya excluye
# estos patrones del CONTEXTO, pero la IA los inventa igual desde el texto.
# Esta red final descarta la afirmación CUPS falsa preservando la referencia
# al servicio.
_PAT_CUPS_SOSPECHOSO = re.compile(
    r"(?:(?:EL|LA|DEL|UN|UNA)\s+)?"
    r"(?:C[ÓO]DIGO\s+CUPS|CUPS(?:\s+DETALLADO)?|C[ÓO]DIGO\s+DE\s+SERVICIO)\s+"
    r"((?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
    r"|(?:19|20)\d{2}-\d{1,2}(?:-\d{1,2})?"
    r"|HUS[\d-]+"
    r"|FE\d{4,}"
    r"|FAC\d{4,})",
    re.IGNORECASE,
)
# Ronda 6 (16-jun-2026 — fix L): factura tratada como "código de glosa".
# Evidencia caso 13: "EL LEVANTAMIENTO DE LA GLOSA 118800 Y EL
# RECONOCIMIENTO INTEGRAL" — 118800 es el número de factura HUS-2026-
# 118800, no un código de glosa (los códigos son alfanuméricos cortos:
# TA0201, CO0701, etc.). Conservador: solo neutraliza después del anclaje
# "GLOSA" (no "CÓDIGO" para no romper CUPS reales como 311400).
_PAT_FACTURA_COMO_GLOSA = re.compile(
    r"(?:(?:LA|EL|DE\s+LA|DE\s+LA\s+PRESENTE)\s+)?"
    r"GLOSA\s+"
    r"(?:N[°º]\s*|N[ÚU]MERO\s+)?"
    r"(\d{6,8})"
    r"(?=[^A-Z0-9]|$)",
    re.IGNORECASE,
)


def _neutralizar_cups_falsos(texto: str) -> str:
    """Sustituye 'CUPS <fecha>' o 'CUPS HUS00...' por 'el procedimiento facturado'.

    Conservador: solo dispara con patrones inequívocamente NO-CUPS (8 dígitos
    yyyymmdd, fechas con guión, prefijos HUS/FE/FAC). Un CUPS real de 4-6
    dígitos jamás coincide.
    """
    if not texto:
        return texto

    def _sub(m):
        return "el procedimiento facturado"

    resultado, n = _PAT_CUPS_SOSPECHOSO.subn(_sub, texto)
    # Fix L: "GLOSA NNNNNN" (donde NNNNNN parece factura) → "la glosa
    # aplicada". Conservador: requiere la palabra GLOSA seguida de 6-8
    # dígitos. No toca códigos de glosa válidos (formato letra+letra+
    # 4 dígitos como TA0201, CO0701).
    resultado, n_fac = _PAT_FACTURA_COMO_GLOSA.subn(
        lambda m: "la glosa aplicada",
        resultado,
    )
    n += n_fac
    if n:
        # Limpieza gramatical: la sustitución puede dejar "facturado facturado"
        # cuando la frase original ya tenía "facturado" después del CUPS.
        resultado = re.sub(r"\b(facturado|facturada)\s+\1\b", r"\1", resultado, flags=re.IGNORECASE)
        resultado = re.sub(r"\b(el|la|del|de\s+la)\s+\1\b", r"\1", resultado, flags=re.IGNORECASE)
        logger.warning(
            f"[CUPS-FALSO] {n} mención(es) de 'CUPS <fecha/factura>' o 'GLOSA <factura>' "
            "neutralizadas en el dictamen final (redes ronda 3 + ronda 6)."
        )
    return resultado


# ── Sanitizer "descomillar citas ALTA" (12-jun-2026, ronda 2 — fix #2) ──
# Evidencia: caso osteosíntesis ENTREGADO con «El pagador reconocerá la
# factura dentro de los veintidós (22) días hábiles...» marcada
# CITA_LITERAL_FALSA ALTA por el verifier. Causa raíz doble: (a) con
# QUALITY_GATE_ENABLED OFF (default) el camino legacy nunca regenera por
# citas — y quitar_citas_invalidas_dinamico solo elimina citas con número
# de norma+año, NO citas literales falsas (sin componentes); (b) con QG ON,
# tras 3 intentos ESCALAR_HUMANO entrega el "mejor" intento CON la cita.
# Red final determinística: la cita falsa pierde las comillas (paráfrasis
# neutra "EN LOS TÉRMINOS DE ...") para que NUNCA se radique una cita
# textual inventada — el contenido argumental se conserva sin atribuirse
# como copia literal.
_PAT_DESCOMILLAR_CHEVRON = re.compile(r"«([^«»]{15,800})»")
# Mismo patrón de atribución del citation_verifier (verbo + comillas).
_PAT_DESCOMILLAR_ATRIBUIDA = re.compile(
    r"((?:ESTABLECE|DISPONE|SEÑALA|SENALA|CONSAGRA|REZA|INDICA|PRECEPTÚA|PRECEPTUA)"
    r"\s*(?:QUE\s*)?(?:TEXTUALMENTE\s*)?:?\s*)"
    r"[\"“‘']([^\"“”‘’']{15,800})[\"”’']",
    re.IGNORECASE,
)


def _descomillar_citas_falsas(texto: str, issues) -> str:
    """Quita las comillas de las citas marcadas CITA_LITERAL_FALSA.

    Recibe el dictamen y los issues del citation_verifier; para cada
    CITA_LITERAL_FALSA reemplaza «X» / "X" por la versión SIN comillas
    precedida de "EN LOS TÉRMINOS DE" (paráfrasis neutra). Solo toca los
    spans que matchean un issue — las citas verificadas quedan intactas.
    """
    if not texto or not issues:
        return texto
    falsas = [i for i in issues if (i or {}).get("tipo") == "CITA_LITERAL_FALSA"]
    if not falsas:
        return texto

    try:
        from app.services.citation_verifier import _normalizar as _norm_cita
    except Exception:
        return texto

    # El issue trae la cita truncada a 140 chars y envuelta en «»; usamos el
    # prefijo normalizado como huella para localizar el span original.
    huellas: list[str] = []
    for i in falsas:
        c = str(i.get("cita") or "").strip().strip("«»").strip()
        if c.endswith("..."):
            c = c[:-3]
        cn = _norm_cita(c)
        if len(cn) >= 15:
            huellas.append(cn)
    if not huellas:
        return texto

    def _es_falsa(contenido: str) -> bool:
        # El dictamen ya está en HTML: un «...» puede traer <br/> adentro,
        # pero el issue del verifier se construyó sobre texto SIN tags
        # (_quitar_html) — se igualan las condiciones antes de comparar.
        cn = _norm_cita(re.sub(r"<[^>]+>", " ", contenido))
        if len(cn) < 15:
            return False
        for h in huellas:
            corte = min(len(h), len(cn), 60)
            if corte >= 15 and cn[:corte] == h[:corte]:
                return True
        return False

    # Ronda 10 (17-jun-2026) — el contexto manda, no la cita. Producción
    # 17-jun (FAMISANAR HUS0000507120): "TAMBIÉN, SE INCUMPLE CON LA CLÁUSULA
    # 5 DEL CONTRATO QUE ESTABLECE: en los términos de Las partes acuerdan
    # ...". El conector salió en minúscula porque la cita interna está en
    # mixed-case, pero el párrafo huésped es CAPS sostenido — se ve roto.
    # Detectamos la mayúscula del párrafo huésped (60 chars antes del span)
    # en lugar de la del contenido citado.
    def _conector_por_contexto(texto_completo: str, span_inicio: int) -> str:
        ventana = texto_completo[max(0, span_inicio - 60) : span_inicio]
        letras = [c for c in ventana if c.isalpha()]
        if letras and (sum(1 for c in letras if c.isupper()) / len(letras)) >= 0.6:
            return "EN LOS TÉRMINOS DE "
        return "en los términos de "

    n_reemplazos = 0

    def _sub_chevron(m: "re.Match[str]") -> str:
        nonlocal n_reemplazos
        contenido = m.group(1)
        if _es_falsa(contenido):
            n_reemplazos += 1
            return _conector_por_contexto(texto, m.start()) + contenido
        return m.group(0)

    def _sub_atribuida(m: "re.Match[str]") -> str:
        nonlocal n_reemplazos
        contenido = m.group(2)
        if _es_falsa(contenido):
            n_reemplazos += 1
            # El verbo de atribución (group 1) ya está en el span; el
            # contexto previo se mide desde el inicio del match completo.
            return m.group(1) + _conector_por_contexto(texto, m.start()) + contenido
        return m.group(0)

    resultado = _PAT_DESCOMILLAR_CHEVRON.sub(_sub_chevron, texto)
    resultado = _PAT_DESCOMILLAR_ATRIBUIDA.sub(_sub_atribuida, resultado)
    if n_reemplazos:
        logger.warning(
            f"[DESCOMILLAR-CITAS] {n_reemplazos} cita(s) literal(es) FALSA(s) "
            "neutralizadas como paráfrasis sin comillas (red final ronda 2)."
        )
    return resultado


# ── Placeholders crudos en el output (12-jun-2026, ronda 2 — fix #6) ──
# Evidencia: dictamen entregado con "INTERPUESTA POR [ENTIDAD], RESPECTO DE
# LA PRESCRIPCIÓN Y EJECUCIÓN DEL [SERVICIO] FACTURADO POR [VALOR REAL]...
# LA GLOSA [CODIGO]". El sanitizer 16a solo cubría "$[...]" con prefijo $.
# MAYÚSCULAS sostenidas dentro de corchetes — no confunde con "[sic]".
_PAT_PLACEHOLDER_CRUDO = re.compile(r"\[([A-ZÁÉÍÓÚÑ_ ]{3,})\]")

_PLACEHOLDER_NEUTRO_VALOR = "EL VALOR INDICADO EN EL EXPEDIENTE"


def _rellenar_placeholders(texto: str, eps: str = "", codigo: str = "", valor: str = "") -> str:
    """Reemplaza placeholders crudos por los datos reales del caso.

    [ENTIDAD]/[EPS] → eps real · [CODIGO]/[CÓDIGO] → código real ·
    [VALOR REAL]/[VALOR] → valor formateado (>0) o frase neutra ·
    [SERVICIO] → "EL SERVICIO FACTURADO". Si tras reemplazar queda CUALQUIER
    [PLACEHOLDER] en mayúsculas, se registra warning (y el post_validator lo
    marca GRAVE en los flujos con Quality Gate).
    """
    if not texto or "[" not in texto:
        return texto

    eps_up = (eps or "").upper().strip()
    eps_txt = eps_up if eps_up and eps_up not in ("OTRA / SIN DEFINIR", "OTRA") else ""
    codigo_txt = (codigo or "").strip()
    if codigo_txt.upper() in ("", "N/A"):
        codigo_txt = ""
    valor_txt = ""
    try:
        from app.utils.moneda import parse_valor_cop as _pvc_ph

        if valor and _pvc_ph(valor) > 0:
            valor_txt = str(valor).strip()
    except Exception:
        valor_txt = ""

    reemplazos = {
        "ENTIDAD": eps_txt or "LA ENTIDAD PAGADORA",
        "EPS": eps_txt or "LA ENTIDAD PAGADORA",
        "ENTIDAD PAGADORA": eps_txt or "LA ENTIDAD PAGADORA",
        "NOMBRE EPS": eps_txt or "LA ENTIDAD PAGADORA",
        "NOMBRE DE LA ENTIDAD": eps_txt or "LA ENTIDAD PAGADORA",
        "CODIGO": codigo_txt or "EL CÓDIGO DE GLOSA APLICADO",
        "CÓDIGO": codigo_txt or "EL CÓDIGO DE GLOSA APLICADO",
        "CODIGO GLOSA": codigo_txt or "EL CÓDIGO DE GLOSA APLICADO",
        "CÓDIGO GLOSA": codigo_txt or "EL CÓDIGO DE GLOSA APLICADO",
        "CODIGO REAL": codigo_txt or "EL CÓDIGO DE GLOSA APLICADO",
        "CÓDIGO REAL": codigo_txt or "EL CÓDIGO DE GLOSA APLICADO",
        "VALOR REAL": valor_txt or _PLACEHOLDER_NEUTRO_VALOR,
        "VALOR": valor_txt or _PLACEHOLDER_NEUTRO_VALOR,
        "VALOR OBJETADO": valor_txt or _PLACEHOLDER_NEUTRO_VALOR,
        "VALOR FACTURADO": valor_txt or _PLACEHOLDER_NEUTRO_VALOR,
        "MONTO": valor_txt or _PLACEHOLDER_NEUTRO_VALOR,
        "MONTO REAL": valor_txt or _PLACEHOLDER_NEUTRO_VALOR,
        "SERVICIO": "EL SERVICIO FACTURADO",
        "DESCRIPCION DEL SERVICIO": "EL SERVICIO FACTURADO",
        "DESCRIPCIÓN DEL SERVICIO": "EL SERVICIO FACTURADO",
        "TIPO DE SERVICIO": "EL SERVICIO FACTURADO",
        "TIPO COMPLETO": "EL CONCEPTO OBJETADO",
        "PROCEDIMIENTO": "EL PROCEDIMIENTO FACTURADO",
        "FECHA": "LA FECHA INDICADA EN EL EXPEDIENTE",
        "FECHA REAL": "LA FECHA INDICADA EN EL EXPEDIENTE",
    }

    def _sub(m: "re.Match[str]") -> str:
        clave = re.sub(r"\s+", " ", m.group(1)).strip()
        return reemplazos.get(clave, m.group(0))

    resultado = _PAT_PLACEHOLDER_CRUDO.sub(_sub, texto)

    # Limpieza gramatical post-reemplazo: "DEL [SERVICIO] FACTURADO" →
    # "DEL EL SERVICIO FACTURADO FACTURADO" sin estos ajustes.
    resultado = re.sub(r"\bDEL\s+EL\s+", "DEL ", resultado, flags=re.IGNORECASE)
    resultado = re.sub(r"\bDE\s+EL\s+SERVICIO\b", "DEL SERVICIO", resultado, flags=re.IGNORECASE)
    resultado = re.sub(
        r"\bSERVICIO\s+FACTURADO\s+FACTURADO\b",
        "SERVICIO FACTURADO",
        resultado,
        flags=re.IGNORECASE,
    )
    resultado = re.sub(
        r"\bLA\s+GLOSA\s+EL\s+C[ÓO]DIGO\s+DE\s+GLOSA\s+APLICADO\b",
        "LA GLOSA APLICADA",
        resultado,
        flags=re.IGNORECASE,
    )

    residuales = _PAT_PLACEHOLDER_CRUDO.findall(resultado)
    if residuales:
        logger.warning(
            f"[PLACEHOLDERS] {len(residuales)} placeholder(s) sin equivalencia tras "
            f"sanitizar: {residuales[:3]} — el dictamen requiere revisión."
        )
    return resultado


# ── Fechas de ratificación EN EL TEXTO (12-jun-2026, ronda 2 — fix #5) ──
# Evidencia: "Fecha radicación: 2026-03-01. Fecha recepción ratificación:
# 2026-05-30" (≈60 días hábiles) y el dictamen ni lo mencionó. El
# texto_fijo_detector solo cubre extemporaneidad de glosa INICIAL con
# campos de BD; aquí las fechas vienen EN EL TEXTO y es una RATIFICACIÓN.
_PAT_FECHA_TEXTO = re.compile(r"(\d{4}-\d{1,2}-\d{1,2})|(\d{1,2}/\d{1,2}/\d{4})")
# Ronda 3 (16-jun-2026): el usuario tipeó "Glosa inicial notificada el
# 10/04/2026 y RATIFICADA por la EPS el 15/06/2026" — formas verbales que el
# patrón anterior (label "FECHA RADICACIÓN:") no atrapaba. Ampliamos:
#   • Radicación: + "GLOSA INICIAL (FUE) NOTIFICADA EL" / "RADICADA EL"
#   • Ratificación: + "RATIFICADA (POR LA EPS) EL" / "RATIFICADO EL"
_PAT_LABEL_RADICACION_TXT = re.compile(
    r"(?:FECHA\s+(?:DE\s+)?)?RADICACI[ÓO]N(?:\s+(?:DE\s+)?(?:LA\s+)?FACTURA)?\s*[:\-–]?\s*"
    r"|(?:LA\s+)?GLOSA(?:\s+INICIAL)?\s+(?:FUE\s+)?(?:NOTIFICAD[AO]|RADICAD[AO])"
    r"(?:\s+(?:POR\s+(?:LA\s+)?(?:EPS|ENTIDAD)))?(?:\s+EL)?\s*[:\-–]?\s*",
    re.IGNORECASE,
)
_PAT_LABEL_RATIFICACION_TXT = re.compile(
    r"(?:FECHA\s+(?:DE\s+)?)?(?:RECEPCI[ÓO]N|NOTIFICACI[ÓO]N)\s+(?:DE\s+(?:LA\s+)?)?"
    r"RATIFICACI[ÓO]N\s*[:\-–]?\s*"
    r"|RATIFICACI[ÓO]N\s+(?:RECIBIDA|NOTIFICADA)(?:\s+EL)?\s*[:\-–]?\s*"
    r"|RATIFICAD[AO](?:\s+(?:POR\s+(?:LA\s+)?(?:EPS|ENTIDAD)))?(?:\s+EL)?\s*[:\-–]?\s*",
    re.IGNORECASE,
)


def _fecha_a_iso(fecha_str: str) -> Optional[str]:
    """ "2026-03-01" o "01/03/2026" → "2026-03-01" (None si no parsea)."""
    s = (fecha_str or "").strip()
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    m_col = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    try:
        if m_iso:
            d = datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        elif m_col:
            d = datetime(int(m_col.group(3)), int(m_col.group(2)), int(m_col.group(1)))
        else:
            return None
        return d.strftime("%Y-%m-%d")
    except ValueError:
        return None


def _fecha_tras_label(texto: str, pat_label: re.Pattern) -> Optional[str]:
    """Primera fecha (ISO o dd/mm/yyyy) dentro de los 30 chars tras el label."""
    for m in pat_label.finditer(texto or ""):
        ventana = texto[m.end() : m.end() + 30]
        m_fecha = _PAT_FECHA_TEXTO.search(ventana)
        if m_fecha and m_fecha.start() <= 5:
            return _fecha_a_iso(m_fecha.group(0))
    return None


def detectar_fechas_en_texto(texto: str) -> dict:
    """Detecta el par radicación → recepción/notificación de RATIFICACIÓN.

    Solo fechas etiquetadas (radicación / recepción-notificación de la
    ratificación) — los demás pares de fechas del texto se ignoran. NO toca
    la lógica de texto_fijo de BD existente: esto alimenta ÚNICAMENTE el
    bloque de prompt "[EXTEMPORANEIDAD DETECTADA]" del flujo analizar().

    Returns:
        {"fecha_radicacion": "YYYY-MM-DD"|None,
         "fecha_ratificacion": "YYYY-MM-DD"|None}
    """
    if not texto:
        return {"fecha_radicacion": None, "fecha_ratificacion": None}
    return {
        "fecha_radicacion": _fecha_tras_label(texto, _PAT_LABEL_RADICACION_TXT),
        "fecha_ratificacion": _fecha_tras_label(texto, _PAT_LABEL_RATIFICACION_TXT),
    }


# Término de referencia para la respuesta de la EPS a la respuesta de la IPS
# (ratificación): Art. 57 Ley 1438/2011. Conservador: 30 días hábiles.
DIAS_HABILES_LIMITE_RATIFICACION = 30


# ── Citas inducidas por la EPS (ronda 5, 16-jun-2026 — fix E) ──
# Evidencia caso 3 (Sanitas): la EPS apoya su glosa en una "Sentencia
# C-313 de 2014" con texto entrecomillado inventado. El dictamen original
# ignoró la cita y argumentó por el otro lado — el gestor humano queda
# con la duda de si esa cita era válida. Detectar: cita textual atribuida
# a NORMA o SENTENCIA dentro del texto de la glosa, para inyectar un
# bloque al prompt que obligue a desvirtuarla EXPLÍCITAMENTE.
_PAT_CITA_INDUCIDA = re.compile(
    # "Sentencia C-313 de 2014 ... 'establece que las IPS...'" o
    # "Circular 066 de 2010 ... 'dispone la devolución...'" — el verbo
    # ("establece", "dispone", "señala") puede ir FUERA o DENTRO de las
    # comillas. El texto entre la norma y la comilla de apertura es
    # variable (corte ≤180 chars) para tolerar "de la Corte
    # Constitucional, que en su parte resolutiva". El verbo se exige
    # cerca de la cita (no en la norma misma).
    #
    # Ronda 6 (16-jun-2026 — fix F): añadidos NOM mexicana, ISO/IEC/IEEE,
    # CONVENIO/ACUERDO/GUÍA. Evidencia caso 12 (Compensar): la EPS citó
    # "NOM-035-STPS-2018" e "ISO 9001:2015 cláusula 8.5.1" como si
    # aplicaran en Colombia — son estándares extranjeros sin valor
    # vinculante. El regex anterior solo cubría LEY/DECRETO/RESOLUCIÓN/
    # CIRCULAR/SENTENCIA, así que estas pasaban sin disparar el bloque.
    r"(SENTENCIA\s+[CTSU][\-‐-―]?\d{1,4}(?:[\-/]\s*|\s+DE\s+|\s+)\d{4}|"
    r"CIRCULAR\s+\d{1,4}(?:\s+DE\s+\d{4})?|"
    r"RESOLUCI[ÓO]N\s+\d{1,4}(?:\s+DE\s+\d{4})?|"
    r"LEY\s+\d{1,4}(?:\s+DE\s+\d{4})?|"
    r"DECRETO\s+\d{1,4}(?:\s+DE\s+\d{4})?|"
    r"NOM[\-‐]?\d{1,4}(?:[\-‐][A-Z]{2,5})?(?:[\-‐]\d{4})?|"
    r"ISO\s+\d{3,5}(?::\d{4})?(?:\s+CL[ÁA]USULA\s+\d+(?:\.\d+){0,3})?|"
    r"IEC\s+\d{3,5}(?::\d{4})?|"
    r"IEEE\s+\d{3,5}(?:\.\d+)?|"
    r"CONVENIO\s+\d{1,4}(?:\s+(?:DE\s+\d{4}|OIT))?|"
    r"ACUERDO\s+\d{1,4}(?:\s+DE\s+\d{4})?|"
    r"GU[ÍI]A\s+(?:[A-Z]{2,6}(?:/[A-Z]{2,6})?|N[°º]\s+\d+|\d+|DE\s+PR[ÁA]CTICA))"
    r"[\s\S]{0,180}?"
    r"['\"‘’“”«»]"
    r"([^'\"‘’“”«»]*?"
    r"(?:ESTABLEC[EI]|DISPON[EI]|SE[NÑ]ALA|ORDENA|DECLARA|DEFINE|DICE|RECONOC[EI])"
    r"[^'\"‘’“”«»]*?)"
    r"['\"‘’“”«»]",
    re.IGNORECASE,
)


def _extraer_citas_inducidas_eps(texto: str) -> list[str]:
    """Citas textuales atribuidas a normas/sentencias dentro del texto de
    la glosa. Devuelve lista de strings normalizados "Norma: «texto»".
    """
    if not texto:
        return []
    out: list[str] = []
    for m in _PAT_CITA_INDUCIDA.finditer(texto):
        norma = re.sub(r"\s+", " ", m.group(1)).strip()
        cita = re.sub(r"\s+", " ", m.group(2)).strip()
        if len(cita) >= 20:
            out.append(f"{norma}: «{cita[:200]}»")
    # Dedup por norma (la misma norma con la misma cita aparece una vez).
    vistos: set[str] = set()
    unicos: list[str] = []
    for c in out:
        if c not in vistos:
            vistos.add(c)
            unicos.append(c)
    return unicos


def _ajustar_score_por_evidencia(score: float, verif_citas, confianza) -> float:
    """Ajusta el gauge "probabilidad de éxito" con la evidencia real.

    Auditoría 10-jun-2026 P1-4: _calcular_score es una heurística estática
    (base 85-99 + bonus por cita REGEX + bonus por longitud) que nunca
    descuenta nada — las citas FABRICADAS subían el score. En paralelo el
    confidence_scorer calcula la señal honesta (cláusulas reales,
    precedente, soportes, citas verificadas) y el gestor veía "92% éxito"
    encima de "41% REFORMULAR". Reglas:
      - Cada cita inválida ALTA descuenta 8 pts; MEDIA descuenta 3.
      - El gauge nunca supera (confianza_real% + 10).
      - Piso 15 para que la barra no desaparezca (sigue siendo una defensa).
    """
    try:
        s = float(score)
        if verif_citas and isinstance(verif_citas, dict):
            issues = verif_citas.get("issues") or []
            altas = sum(1 for i in issues if (i or {}).get("severidad") == "ALTA")
            medias = sum(1 for i in issues if (i or {}).get("severidad") == "MEDIA")
            s -= 8.0 * altas + 3.0 * medias
        if confianza and isinstance(confianza, dict):
            conf = confianza.get("score")
            if isinstance(conf, (int, float)) and 0 <= conf <= 1:
                s = min(s, conf * 100.0 + 10.0)
        return round(max(15.0, min(100.0, s)), 1)
    except Exception:
        return score


_SUAVIZAR_PATTERNS = [
    # Apertura obligatoria: nunca "RESPETUOSAMENTE" en la primera frase
    (r"\bESE\s+HUS\s+RESPETUOSAMENTE\s+NO\s+ACEPTA\b", "ESE HUS NO ACEPTA"),
    # ═══ REGISTRO COLOQUIAL → TÉCNICO-JURÍDICO ═══
    # (detectados en respuestas reales que debilitan la defensa)
    (r"\bLAS\s+RAZONES\s+SON\s+CLARAS[:\.,]?", "POR LAS SIGUIENTES RAZONES:"),
    (r"\bLO\s+CUAL\s+NO\s+ES\s+V[ÁA]LIDO\b", "LO CUAL NO SE AJUSTA AL MARCO CONTRACTUAL"),
    (r"\bA\s+CONVENIENCIA\b", "DE MANERA UNILATERAL"),
    (
        r"\bPAGO\s+COMPLETO\s+DEL\s+VALOR\s+FACTURADO\b",
        "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO",
    ),
    (r"\bEL\s+PAGO\s+COMPLETO\b", "EL RECONOCIMIENTO ÍNTEGRO"),
    (r"\bPAGAR\s+COMPLETO\b", "RECONOCER ÍNTEGRAMENTE"),
    (r"\bES\s+CLARO\s+QUE\b", "RESULTA EVIDENTE QUE"),
    (r"\b(?:SIMPLEMENTE|B[ÁA]SICAMENTE|OBVIAMENTE|CLARAMENTE)\s+", ""),
    (r"\bELLA\s+MISMA\s+FIRM[ÓO]\b", "SUSCRITO POR LA ENTIDAD PAGADORA"),
    (r"\bQUE\s+LA\s+EPS\s+ELLA\s+MISMA\b", "QUE LA ENTIDAD PAGADORA"),
    (r"\bNO\s+EST[ÁA]\s+BIEN\b", "NO RESULTA PROCEDENTE"),
    (r"\bNO\s+ES\s+BUENA\s+IDEA\b", "NO RESULTA PROCEDENTE"),
    (
        r"\bEST[ÁA]\s+USANDO\s+UNA\s+TARIFA\s+DIFERENTE\b",
        "APLICA UNA TARIFA DIFERENTE A LA PACTADA",
    ),
    (r"\bSIN\s+APLICAR\s+DICHO\s+DESCUENTO\b", "SIN APLICAR EL DESCUENTO CONTRACTUAL CONVENIDO"),
    # Exigir → Solicitar
    (
        r"\bSE\s+EXIGE\s+EL\s+LEVANTAMIENTO\s+INMEDIATO\s+Y\s+DEFINITIVO\b",
        "SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO",
    ),
    (
        r"\bSE\s+EXIGE\s+EL\s+LEVANTAMIENTO\s+INMEDIATO\b",
        "SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO",
    ),
    (r"\bSE\s+EXIGE\s+EL\s+LEVANTAMIENTO\b", "SE SOLICITA EL LEVANTAMIENTO"),
    (r"\bSE\s+EXIGE\s+EL\s+PAGO\s+[ÍI]NTEGRO\b", "SE SOLICITA EL RECONOCIMIENTO ÍNTEGRO"),
    (r"\bSE\s+EXIGE\s+EL\s+RECONOCIMIENTO\b", "SE SOLICITA EL RECONOCIMIENTO"),
    (r"\bSE\s+EXIGE\b(?!\s+EL)", "SE SOLICITA"),
    # Obligar → establece el deber
    (
        r"\bOBLIGA\s+A\s+LA\s+ENTIDAD\s+PAGADORA\s+A\s+RECONOCER\b",
        "ESTABLECE EL DEBER DE RECONOCER",
    ),
    (r"\bOBLIGA\s+A\s+LA\s+EPS\s+A\s+RECONOCER\b", "ESTABLECE EL DEBER DE RECONOCER"),
    (r"\bOBLIGA\s+A\s+LAS\s+ENTIDADES?\b", "ESTABLECE EL DEBER DE LAS ENTIDADES"),
    # Incumplimiento hostil → diferencia susceptible
    (
        r"\bCONFIGURA\s+UN\s+INCUMPLIMIENTO\s+CONTRACTUAL\s+INJUSTIFICADO\b",
        "CORRESPONDE A UNA DIFERENCIA SUSCEPTIBLE DE SUBSANACIÓN",
    ),
    (r"\bINCUMPLIMIENTO\s+CONTRACTUAL\s+INJUSTIFICADO\b", "DIFERENCIA SUSCEPTIBLE DE SUBSANACIÓN"),
    (
        r"\bAFECTA\s+DIRECTAMENTE\s+EL\s+FLUJO\s+DE\s+RECURSOS\s+DEL\s+HOSPITAL\b",
        "AFECTA EL FLUJO DE RECURSOS INSTITUCIONALES",
    ),
    # Acusaciones
    (
        r"\bLO\s+CUAL\s+NO\s+SE\s+HA\s+CUMPLIDO\s+EN\s+ESTE\s+CASO\b\.?",
        "SE SOLICITA SU APLICACIÓN EN EL PRESENTE CASO.",
    ),
    (
        r"\bNO\s+FUE\s+RESPETADA\s+POR\s+LA\s+ENTIDAD\s+PAGADORA\b",
        "REQUIERE SU APLICACIÓN CONFORME A LO CONVENIDO",
    ),
    (
        r"\bNO\s+FUE\s+RESPETADA\s+POR\s+LA\s+EPS\b",
        "REQUIERE SU APLICACIÓN CONFORME A LO CONVENIDO",
    ),
    (r"\bCONSTITUYE\s+UN\s+ACTO\s+ABUSIVO\s+E\s+IMPROCEDENTE\b", "AMERITA SER REVISADA"),
    (r"\bCONSTITUYE\s+UN\s+ACTO\s+ABUSIVO\b", "AMERITA SER REVISADA"),
    (r"\bACTO\s+ABUSIVO\s+E\s+IMPROCEDENTE\b", "OBJECIÓN SUSCEPTIBLE DE CONCILIACIÓN"),
    (r"\bCARECE\s+DE\s+TODO\s+SUSTENTO\s+LEGAL\b", "REQUIERE MAYOR SUSTENTO"),
    (
        r"\bCARECE\s+DE\s+SUSTENTO\s+CONTRACTUAL\s+Y\s+LEGAL\b",
        "REQUIERE MAYOR SUSTENTO CONTRACTUAL Y LEGAL",
    ),
    (r"\bCARECE\s+DE\s+SUSTENTO\b", "REQUIERE MAYOR SUSTENTO"),
    # Frases redundantes
    (r"\bSE\s+REFUERZA\s+LA\s+ARGUMENTACI[ÓO]N\s+DE\s+QUE\b", "SE RATIFICA QUE"),
]

_FRASES_ROTAS_PATTERNS = [
    (
        r"RECONOCIMIENTO\s+[ÍI]NTEGRO\s+DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
        "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO",
    ),
    (
        r"RECONOCIMIENTO\s+DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
        "RECONOCIMIENTO DEL VALOR FACTURADO",
    ),
    (
        r"VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
        r"VALOR \1 EN EL EXPEDIENTE",
    ),
    (
        r"FACTURAD[OA]\s+POR\s+VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
        r"FACTURADO SEGÚN CONSTA EN EL EXPEDIENTE",
    ),
    (
        r"Y\s+RECONOCIDO\s+SOLO\s+POR\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
        "Y RECONOCIDO PARCIALMENTE POR LA ENTIDAD PAGADORA",
    ),
    (
        r"RETENCI[ÓO]N\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
        "LA DIFERENCIA INDICADA EN EL EXPEDIENTE",
    ),
    (r"\bDE\s+EL\s+VALOR\b", "DEL VALOR"),
]


def _suavizar_tono(texto: str) -> str:
    """Aplica patrones de tono conciliador y corrige frases rotas.

    Se ejecuta en TODOS los caminos (texto fijo, plantilla, IA) para
    garantizar un tono institucional uniforme. La defensa jurídica se
    preserva; solo se cambia la forma.
    """
    if not texto:
        return texto
    # Eliminar NIT del pagador en parentesis (bloque completo, con posibles
    # espacios, comas, puntos). Patrones que la IA suele generar:
    #   "(NIT 901.541.137-1)"  → quita el parentesis completo
    #   "(NIT 901541137-1)"
    #   ", NIT 901.541.137-1,"  → quita la clausula
    #   " NIT 901.541.137-1"    → quita el token
    # Usamos MAYUSCULAS/minúsculas para cubrir ambos.
    texto = re.sub(r"\s*\([Nn][Ii][Tt][\s\.]*\d[\d\.\s\-]*\d\s*\)", "", texto)
    texto = re.sub(r",?\s*[Nn][Ii][Tt][\s\.]*\d[\d\.\s\-]*\d,?", "", texto)
    # Limpiar dobles espacios y dobles comas que quedan tras el recorte
    texto = re.sub(r"\s+,", ",", texto)
    texto = re.sub(r",\s*,", ",", texto)
    texto = re.sub(r"\s{2,}", " ", texto)
    # Placeholders literales residuales
    texto = re.sub(
        r"\$\s*\[[A-Z_ ]+\]",
        "EL VALOR INDICADO EN EL EXPEDIENTE",
        texto,
        flags=re.IGNORECASE,
    )
    # Frases rotas (primero, para que el suavizador no sobre-escriba)
    for pat, repl in _FRASES_ROTAS_PATTERNS:
        texto = re.sub(pat, repl, texto, flags=re.IGNORECASE)
    # Tono hostil → conciliador
    for pat, repl in _SUAVIZAR_PATTERNS:
        texto = re.sub(pat, repl, texto, flags=re.IGNORECASE)
    return texto


def generar_texto_tarifa_match(
    codigo_glosa: str,
    valor_objetado: float,
    info_tarifa: dict,
) -> str:
    """Plantilla determinística cuando existe match perfecto entre el valor
    facturado por HUS y la tarifa pactada en el contrato con la EPS.

    Se usa cuando el banner de tarifa pactada detecta DEFENDER_TOTAL
    con tolerancia < $1. Evita llamar al LLM (ahorro ~8k tokens por
    glosa) y genera un argumento sólido con los datos duros del contrato.

    info_tarifa viene de tarifa_lookup_service.evaluar_glosa_tarifa() y
    contiene: tarifa.codigo_cups/descripcion/contrato_numero/modalidad,
    valor_pactado_calc, etc.
    """
    t = info_tarifa.get("tarifa") or {}
    pact = float(info_tarifa.get("valor_pactado_calc") or 0.0)
    val_fact = float(info_tarifa.get("valor_facturado") or 0.0)
    val_obj_fmt = f"$ {int(valor_objetado):,}".replace(",", ".")
    pact_fmt = f"$ {int(pact):,}".replace(",", ".")
    fact_fmt = f"$ {int(val_fact):,}".replace(",", ".") if val_fact > 0 else pact_fmt
    contrato = t.get("contrato_numero") or "contrato vigente entre las partes"
    eps = t.get("eps") or "la entidad pagadora"
    cups = t.get("codigo_cups") or "—"
    desc = (t.get("descripcion") or "el servicio facturado").upper()
    modalidad = t.get("modalidad") or "pactada"
    fuente = t.get("fuente_archivo") or "catálogo oficial"

    return (
        f"ESE HUS NO ACEPTA LA GLOSA {codigo_glosa} INTERPUESTA POR {eps.upper()} "
        f"POR VALOR DE {val_obj_fmt}, TODA VEZ QUE EL VALOR FACTURADO ({fact_fmt}) "
        f"COINCIDE EXACTAMENTE CON LA TARIFA PACTADA EN EL {contrato} PARA EL CUPS "
        f"{cups} — {desc} — BAJO LA MODALIDAD {modalidad}. "
        f"LA IDENTIDAD ENTRE VALOR FACTURADO Y VALOR PACTADO CONVIERTE ESTA GLOSA "
        f"EN IMPROCEDENTE: LA ENTIDAD PAGADORA NO PUEDE DESCONOCER UNILATERALMENTE "
        f"EL VALOR QUE ELLA MISMA PACTÓ, POR APLICACIÓN DEL ARTÍCULO 871 DEL CÓDIGO "
        f"DE COMERCIO («LOS CONTRATOS DEBERÁN CELEBRARSE Y EJECUTARSE DE BUENA FE») "
        f"Y DEL ARTÍCULO 1602 DEL CÓDIGO CIVIL («TODO CONTRATO LEGALMENTE CELEBRADO "
        f"ES UNA LEY PARA LOS CONTRATANTES»). EN CONSECUENCIA, SE SOLICITA "
        f"RESPETUOSAMENTE EL LEVANTAMIENTO INMEDIATO DE LA GLOSA Y EL RECONOCIMIENTO "
        f"ÍNTEGRO DEL VALOR FACTURADO ({fact_fmt}). LA ENTIDAD PAGADORA CUENTA CON "
        f"10 DÍAS HÁBILES PARA PRONUNCIARSE CONFORME AL ARTÍCULO 57 DE LA LEY 1438 "
        f"DE 2011; DE NO HACERLO, OPERARÁ EL SILENCIO A FAVOR DEL PRESTADOR. "
        f"FUENTE DEL VALOR PACTADO: {fuente}. COMUNICACIONES: CARTERA@HUS.GOV.CO, "
        f"GLOSASYDEVOLUCIONES@HUS.GOV.CO."
    )


def generar_texto_aceptacion_total(
    codigo_glosa: str = "", valor: str = "", servicio: str = ""
) -> str:
    """Plantilla RE9702 — GLOSA ACEPTADA AL 100%.

    El auditor decidió aceptar la glosa completa. ESE HUS reconoce la
    objeción y aplicará nota crédito. No hay argumento jurídico; es
    una declaración formal de aceptación.
    """
    cod = codigo_glosa or "INDICADO EN EL EXPEDIENTE"
    val = (
        valor
        if valor and valor.strip() not in ("$ 0.00", "$0.00", "$ 0", "")
        else "EL VALOR INDICADO EN EL EXPEDIENTE"
    )
    srv_txt = f" RESPECTO DEL SERVICIO {servicio.upper()}" if servicio else ""
    return (
        f"ESE HUS ACEPTA LA GLOSA APLICADA BAJO EL CÓDIGO {cod} POR {val}"
        f"{srv_txt}, RECONOCIENDO LA OBJECIÓN PLANTEADA POR LA ENTIDAD "
        f"PAGADORA. SE PROCEDERÁ CON LA EMISIÓN DE LA CORRESPONDIENTE "
        f"NOTA CRÉDITO Y AJUSTE DE LA FACTURACIÓN SEGÚN LA NORMATIVA "
        f"VIGENTE (RESOLUCIÓN 2284 DE 2023 - MANUAL ÚNICO DE GLOSAS). "
        f"CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: "
        f"CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
    )


def generar_texto_aceptacion_parcial(
    codigo_glosa: str = "",
    valor_objetado: float = 0.0,
    valor_aceptado: float = 0.0,
    servicio: str = "",
) -> str:
    """Plantilla RE9801 — GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE.

    El auditor acepta parte de la glosa (valor_aceptado) y mantiene
    la defensa sobre la diferencia. Requiere argumento hybrid pero
    aquí generamos solo la sección de aceptación; la defensa de la
    diferencia la genera la IA aparte.
    """
    cod = codigo_glosa or "INDICADO EN EL EXPEDIENTE"
    val_obj = f"${valor_objetado:,.0f}".replace(",", ".") if valor_objetado else "EL VALOR INDICADO"
    val_ace = f"${valor_aceptado:,.0f}".replace(",", ".") if valor_aceptado else "$0"
    diferencia = max(0, valor_objetado - valor_aceptado)
    val_dif = f"${diferencia:,.0f}".replace(",", ".")
    srv_txt = f" RESPECTO DEL SERVICIO {servicio.upper()}" if servicio else ""
    return (
        f"ESE HUS ACEPTA PARCIALMENTE LA GLOSA APLICADA BAJO EL CÓDIGO "
        f"{cod}{srv_txt}. DEL VALOR TOTAL OBJETADO ({val_obj}), SE "
        f"RECONOCE COMO PROCEDENTE LA SUMA DE {val_ace}, SOBRE LA CUAL "
        f"SE EMITIRÁ LA CORRESPONDIENTE NOTA CRÉDITO. LA DIFERENCIA DE "
        f"{val_dif} NO ES ACEPTADA Y SE MANTIENE LA DEFENSA TÉCNICA "
        f"CONFORME AL ARGUMENTO JURÍDICO DESARROLLADO EN LA RESPUESTA "
        f"PRINCIPAL, CON FUNDAMENTO EN LA NORMATIVA VIGENTE (RESOLUCIÓN "
        f"2284 DE 2023 - MANUAL ÚNICO DE GLOSAS, ART. 57 LEY 1438/2011). "
        f"CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: "
        f"CARTERA@HUS.GOV.CO."
    )


TEXTO_RATIFICADA = (
    "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE "
    "DE LA GLOSA INICIAL Y SE DA CONTINUACIÓN AL PROCESO DE CONFORMIDAD CON EL ARTÍCULO "
    "57 DE LA LEY 1438 DE 2011 Y EL ARTÍCULO 20 DEL DECRETO 4747 DE 2007. SE SOLICITA "
    "LA PROGRAMACIÓN DE LA FECHA DE CONCILIACIÓN DE AUDITORÍA MÉDICA Y/O TÉCNICA ENTRE "
    "LAS PARTES. DE NO LLEGARSE A ACUERDO, SE ELEVARÁ EL CONFLICTO ANTE LA "
    "SUPERINTENDENCIA NACIONAL DE SALUD SEGÚN LO DISPUESTO EN EL ART. 126 DE LA LEY "
    "1438/2011. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO INSTITUCIONAL: "
    "CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO, VENTANILLA ÚNICA DE LA ESE HUS "
    "CARRERA 33 NO. 28-126. NOTA: DE ACUERDO CON EL ARTÍCULO 57 DE LA LEY 1438 DE 2011, "
    "DE NO OBTENERSE RESPUESTA A LA GLOSA RATIFICADA EN LOS TÉRMINOS ESTABLECIDOS, "
    "SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN."
)


# ─── Texto fijo: DISPENSARIO MEDICO BUCARAMANGA (DMBUG) — concepto TARIFAS ───
# Pedido por Yesid (abr 2026, hasta nueva orden): toda glosa de
# DISPENSARIO MEDICO con código TA* debe responderse con este texto
# canónico institucional, sin ir al motor IA. Cita el contrato
# 440-DIGSA/DMBUG-2025 con su anexo de 7.141 ítems tarifados y refuta
# el argumento de "agotamiento presupuestal".
TEXTO_DMBUG_TARIFAS = (
    "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE TARIFAS INTERPUESTA POR DMBUG "
    "SOBRE LOS SERVICIOS EN MENCION. ENTRE LAS PARTES SE ENCUENTRA SUSCRITO Y "
    "VIGENTE EL CONTRATO INTERADMINISTRATIVO No. 440-DIGSA/DMBUG-2025 "
    "(PROCESO CD477), CON PLAZO HASTA 30/07/2026, QUE EN SU CLÁUSULA SEGUNDA "
    "– PARÁGRAFO 1 INCORPORA EL ANEXO No. 1 CON 7.141 ÍTEMS TARIFADOS, ENTRE "
    "LOS CUALES SE ENCUENTRA LOS SERVICIOS FACTURADOS. LA AFIRMACIÓN DE "
    "INEXISTENCIA DE CONTRATO ES INEXACTA. EL ARGUMENTO DE AGOTAMIENTO "
    "PRESUPUESTAL NO CONSTITUYE CAUSAL CONTRACTUAL NI LEGAL PARA SUSTITUIR "
    "UNILATERALMENTE LAS TARIFAS PACTADAS POR SOAT, EN VIRTUD DE LOS "
    'ARTÍCULOS 1602 Y 1603 DEL CÓDIGO CIVIL ("TODO CONTRATO LEGALMENTE '
    'CELEBRADO ES UNA LEY PARA LOS CONTRATANTES"), 871 DEL CÓDIGO DE '
    "COMERCIO (BUENA FE CONTRACTUAL), 5 Y 27 DE LA LEY 80 DE 1993 (DERECHO A "
    "LA REMUNERACIÓN PACTADA Y ECUACIÓN CONTRACTUAL), DECRETO-LEY 1795 DE "
    "2000 (RÉGIMEN DEL SUBSISTEMA DE SALUD DE LAS FF.MM.), ACUERDO 002 DE "
    "2001 DEL CSSMP, DECRETO 4747 DE 2007 Y RESOLUCIÓN 3047 DE 2008 (MANUAL "
    "ÚNICO DE GLOSAS). EL EVENTUAL AGOTAMIENTO PRESUPUESTAL ES "
    "RESPONSABILIDAD DEL DMBUG (ART. 71 DEL DECRETO 111/1996) Y NO PUEDE "
    "TRASLADARSE AL PRESTADOR. ASIMISMO, EL DECRETO 2423 DE 1996 OPERA EN "
    "AUSENCIA DE PACTO; HABIENDO CONTRATO VIGENTE, NO PROCEDE COMO CRITERIO "
    "SUSTITUTIVO. SE SOLICITA EL LEVANTAMIENTO ÍNTEGRO DE LA GLOSA Y EL "
    "RECONOCIMIENTO DEL VALOR PACTADO EN EL ANEXO No. 1 DEL CONTRATO "
    "440-DIGSA/DMBUG-2025."
)


def _es_dispensario_medico(eps: str) -> bool:
    """Detecta si la EPS es Dispensario Médico Bucaramanga (DMBUG).
    Acepta variantes:
      DISPENSARIO MEDICO, DISPENSARIO MEDICO BUCARAMANGA, DISPENSARIO
      MEDICO BUCARAMANG (truncado del DGH), DMBUG, U220311 - DIRECCION
      DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG, etc.
    """
    if not eps:
        return False
    e = eps.upper().strip()
    return "DISPENSARIO MEDICO" in e or "DMBUG" in e or "DIGSA" in e or "U220311" in e


def limpiar_cierre_extemporanea_indebido(
    texto: str,
    es_ratificacion: bool = False,
    es_extemporanea: bool = False,
    codigo_respuesta: str = "",
) -> str:
    """Quita el cierre canónico de RATIFICADAS/EXTEMPORÁNEAS cuando NO
    aplica (es decir, cuando la respuesta es defensiva normal, no es
    una ratificación ni una extemporánea).

    Directiva institucional ESE HUS (mayo 2026 — Yesid): el cierre
    «...10 DÍAS HÁBILES PARA PRONUNCIARSE... MESA DE CONCILIACIÓN...
    COMUNICACIONES: CARTERA@HUS.GOV.CO...» SOLO debe aparecer en:
      - Respuestas a glosas RATIFICADAS (es_ratificacion=True, RE9601/RE9602)
      - Respuestas a glosas EXTEMPORÁNEAS (es_extemporanea=True, RE9501/RE9502)
    En CUALQUIER otra defensa (RE9901 normal, RE9702, RE9801) se limpia
    porque infla el dictamen sin aportar valor jurídico.

    El sanitizer es idempotente: aplicarlo varias veces no rompe nada.
    """
    if not texto or not isinstance(texto, str):
        return texto

    # ¿La respuesta SÍ debe llevar el cierre?
    cod = (codigo_respuesta or "").upper().strip()
    codigos_cierre_obligatorio = {"RE9501", "RE9502", "RE9601", "RE9602"}
    if es_ratificacion or es_extemporanea or cod in codigos_cierre_obligatorio:
        return texto

    # Para todos los demás códigos (RE9901 normal, RE9702, RE9801),
    # limpiamos. Patrones tolerantes a variaciones de mayúsculas y
    # espacios. Estrategia: hacer match desde el INICIO del cierre
    # ("LA ENTIDAD PAGADORA CUENTA CON 10..." o "DE PERSISTIR..." o
    # "COMUNICACIONES:...") hasta que termine en correo @hus.gov.co.
    import re as _re

    patrones_cierre = [
        # Variante completa: "LA ENTIDAD PAGADORA CUENTA CON 10 DÍAS..."
        # hasta GLOSASYDEVOLUCIONES@HUS.GOV.CO.
        r"\s*LA\s+ENTIDAD\s+PAGADORA\s+CUENTA\s+CON\s+10\s+D[ÍI]AS\s+H[ÁA]BILES[\s\S]*?GLOSASYDEVOLUCIONES@HUS\.GOV\.CO\.",
        # Variante "10 días" sin glosasydevoluciones, hasta CARTERA@HUS
        r"\s*LA\s+ENTIDAD\s+PAGADORA\s+CUENTA\s+CON\s+10\s+D[ÍI]AS\s+H[ÁA]BILES[\s\S]*?CARTERA@HUS\.GOV\.CO\.",
        # Variante sin "PAGADORA": "LA ENTIDAD CUENTA CON 10 DÍAS..."
        # (frecuente en Groq llama-3.3 — directiva mayo 2026)
        r"\s*LA\s+ENTIDAD\s+CUENTA\s+CON\s+10\s+D[ÍI]AS\s+H[ÁA]BILES[\s\S]*?GLOSASYDEVOLUCIONES@HUS\.GOV\.CO\.",
        r"\s*LA\s+ENTIDAD\s+CUENTA\s+CON\s+10\s+D[ÍI]AS\s+H[ÁA]BILES[\s\S]*?CARTT?ERA@HUS\.GOV\.CO\.",
        # Variante "DE PERSISTIR... mesa de conciliación... correos"
        r"\s*DE\s+PERSISTIR\s+LA\s+OBJECI[ÓO]N[\s\S]*?GLOSASYDEVOLUCIONES@HUS\.GOV\.CO\.",
        r"\s*DE\s+PERSISTIR\s+LA\s+OBJECI[ÓO]N[\s\S]*?CARTT?ERA@HUS\.GOV\.CO\.",
        # Variante "EN SUBSIDIO... mesa de conciliación... correos"
        r"\s*EN\s+SUBSIDIO[\s\S]*?GLOSASYDEVOLUCIONES@HUS\.GOV\.CO\.",
        r"\s*EN\s+SUBSIDIO[\s\S]*?CARTT?ERA@HUS\.GOV\.CO\.",
        # Variante "COMUNICACIONES: ..." con ambos correos
        r"\s*COMUNICACIONES:\s*CARTT?ERA@HUS\.GOV\.CO[^.]*?GLOSASYDEVOLUCIONES@HUS\.GOV\.CO\.",
        # Variante "COMUNICACIONES: ..." con solo CARTERA
        r"\s*COMUNICACIONES:\s*CARTT?ERA@HUS\.GOV\.CO\.",
        # Variante "CUALQUIER INFORMACIÓN AL CORREO..." con ambos
        r"\s*CUALQUIER\s+INFORMACI[ÓO]N\s+A(?:L\s+CORREO\s+ELECTR[ÓO]NICO\s+INSTITUCIONAL)?:?\s*CARTT?ERA@HUS\.GOV\.CO[^.]*?GLOSASYDEVOLUCIONES@HUS\.GOV\.CO\.",
        # Variante "CUALQUIER INFORMACIÓN..." solo CARTERA
        r"\s*CUALQUIER\s+INFORMACI[ÓO]N\s+A(?:L\s+CORREO\s+ELECTR[ÓO]NICO\s+INSTITUCIONAL)?:?\s*CARTT?ERA@HUS\.GOV\.CO\.",
        # Variante "SE EXTIENDE/INVITA UNA INVITACIÓN A LA MESA DE CONCILIACIÓN..."
        # (Groq la usa antes de los emails — mayo 2026)
        r"\s*SE\s+EXTIENDE\s+UNA\s+INVITACI[ÓO]N\s+A\s+LA\s+MESA\s+DE\s+CONCILIACI[ÓO]N[\s\S]*?CARTT?ERA@HUS\.GOV\.CO\.",
        r"\s*SE\s+INVITA\s+A\s+LA\s+(?:ENTIDAD\s+PAGADORA\s+A\s+(?:UNA|LA)\s+)?MESA\s+DE\s+CONCILIACI[ÓO]N[\s\S]*?CARTT?ERA@HUS\.GOV\.CO\.",
        # Variante combinada: "LAS COMUNICACIONES DEBERÁN/PUEDEN DIRIGIRSE..."
        r"\s*LAS\s+COMUNICACIONES\s+(?:DEBER[ÁA]N|PUEDEN)\s+(?:DIRIGIRSE|SER\s+DIRIGIDAS)[\s\S]*?CARTT?ERA@HUS\.GOV\.CO\.",
    ]
    out = texto
    for pat in patrones_cierre:
        out = _re.sub(pat, "", out, flags=_re.IGNORECASE | _re.DOTALL)
    # Limpiar espacios dobles + tags HTML adyacentes vacíos
    out = _re.sub(r"\s{2,}", " ", out)
    out = _re.sub(r"<p>\s*</p>", "", out)
    return out.strip()


def limpiar_palabra_injustificado(texto: str, codigo_respuesta: str = "") -> str:
    """Reemplaza todas las formas de "injustificado/a/os/as" por sinónimos
    profesionales que NO contengan la raíz "injustific".

    Directiva institucional ESE HUS (mayo 2026 — Yesid): la palabra no
    debe aparecer en NINGUNA respuesta generada (apertura, cuerpo,
    fundamento, petición). Esta función es idempotente y safe en
    múltiples pases.

    EXCEPCION (ampliacion mayo 2026): cuando el codigo_respuesta es RE9602
    ('Glosa Injustificada al 100% — IPS aporta evidencia que lo demuestra'),
    la palabra SI debe aparecer porque ESE es el concepto canonico del
    catalogo oficial (catalogo_glosas.py). En ese caso retornamos el texto
    SIN modificar.

    Reemplazos para todos los demas casos:
      • Frases compuestas (más específicas primero):
        - "DESCUENTOS INJUSTIFICADOS" → "DESCUENTOS UNILATERALES"
        - "RETRASO INJUSTIFICADO"     → "RETRASO INDEBIDO"
        - "INCUMPLIMIENTO INJUSTIFICADO" → "INCUMPLIMIENTO CONTRACTUAL"
        - "GLOSA INJUSTIFICADA"       → "GLOSA IMPROCEDENTE"
        - "GLOSAS INJUSTIFICADAS"     → "GLOSAS IMPROCEDENTES"
      • Apertura: limpia adjetivos colados entre GLOSA y APLICADA.
      • Palabra suelta: INJUSTIFICAD(O/A/OS/AS) → IMPROCEDENTE/S.
    Preserva mayúsculas/minúsculas del original.
    """
    if not texto:
        return texto
    # EXCEPCION RE9602: la palabra SI debe aparecer (concepto canonico)
    if (codigo_respuesta or "").upper().strip() == "RE9602":
        return texto
    out = texto
    # Apertura — primero los adjetivos calificativos colados.
    out = re.sub(
        r"\bLA\s+GLOSA\s+(INJUSTIFICADA|INDEBIDA|IMPROCEDENTE|INFUNDADA|INCORRECTA|ERRÓNEA|ERRONEA)\s+APLICADA\b",
        "LA GLOSA APLICADA",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bACEPTA\s+LA\s+GLOSA\s+(INJUSTIFICADA|INDEBIDA|IMPROCEDENTE|INFUNDADA|INCORRECTA|ERRÓNEA|ERRONEA)\b(?!\s+APLICADA)",
        "ACEPTA LA GLOSA",
        out,
        flags=re.IGNORECASE,
    )

    # Frases compuestas con "injustificado/a/os/as" — preservando case.
    def _frase(reemplazo_upper: str):
        def _r(m):
            original = m.group(0)
            if original.isupper():
                return reemplazo_upper
            if original.islower():
                return reemplazo_upper.lower()
            # Mixed: capitalize cada palabra
            return " ".join(w.capitalize() for w in reemplazo_upper.split())

        return _r

    out = re.sub(
        r"\bDESCUENTOS\s+INJUSTIFICADOS\b",
        _frase("DESCUENTOS UNILATERALES"),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bDESCUENTO\s+INJUSTIFICADO\b", _frase("DESCUENTO UNILATERAL"), out, flags=re.IGNORECASE
    )
    out = re.sub(
        r"\bRETRASO\s+INJUSTIFICADO\b", _frase("RETRASO INDEBIDO"), out, flags=re.IGNORECASE
    )
    out = re.sub(
        r"\bINCUMPLIMIENTO\s+INJUSTIFICADO\b",
        _frase("INCUMPLIMIENTO CONTRACTUAL"),
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\bGLOSA\s+INJUSTIFICADA\b", _frase("GLOSA IMPROCEDENTE"), out, flags=re.IGNORECASE
    )
    out = re.sub(
        r"\bGLOSAS\s+INJUSTIFICADAS\b", _frase("GLOSAS IMPROCEDENTES"), out, flags=re.IGNORECASE
    )

    # Palabra suelta — preservando case
    def _repl(m):
        terminacion = m.group(1)
        original = m.group(0)
        plural = terminacion.lower() in ("os", "as")
        sustituto = "IMPROCEDENTES" if plural else "IMPROCEDENTE"
        if original.isupper():
            return sustituto
        if original.islower():
            return sustituto.lower()
        # Mixed case: capitalizar
        return sustituto.capitalize()

    out = re.sub(r"\bINJUSTIFICAD(OS|AS|O|A)\b", _repl, out, flags=re.IGNORECASE)
    return out


def generar_texto_extemporanea(dias: int) -> str:
    """Texto FIJO canónico HUS para glosas extemporáneas (RE9502).

    Es IMPORTANTE que sea 100% fijo — no pasa por IA ni por suavizador —
    para (1) garantizar tono firme consistente y (2) no gastar tokens de
    IA en un caso cuyo argumento es mecánico. El suavizador también se
    salta cuando el `arg_limpio` coincide con esta plantilla.
    """
    return (
        "ESE HUS NO ACEPTA GLOSA EXTEMPORÁNEA. AL HABERSE SUPERADO EL PLAZO LEGAL DE "
        f"20 DÍAS HÁBILES ESTABLECIDO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 "
        f"(HAN TRANSCURRIDO {dias} DÍAS HÁBILES) SIN QUE NUESTRA INSTITUCIÓN RECIBIERA "
        f"NOTIFICACIÓN FORMAL DE LAS OBJECIONES, HA OPERADO DE PLENO DERECHO EL FENÓMENO "
        f"JURÍDICO DE LA ACEPTACIÓN TÁCITA DE LA FACTURA. EN CONSECUENCIA, HA PRECLUIDO "
        f"DEFINITIVAMENTE LA OPORTUNIDAD LEGAL DE LA EPS PARA AUDITAR, GLOSAR O RETENER "
        f"LOS RECURSOS. SE EXIGE EL LEVANTAMIENTO INMEDIATO Y DEFINITIVO DE LA TOTALIDAD "
        f"DE LAS GLOSAS APLICADAS. CUALQUIER INFORMACIÓN A CARTERA@HUS.GOV.CO, "
        f"GLOSASYDEVOLUCIONES@HUS.GOV.CO."
    )


# Keywords que identifican ASEGURADORAS SOAT/ARL/PÓLIZAS sin contrato (pagos
# bajo Manual Tarifario SOAT vigente — Circular 047/2025 MinSalud + UVB 2026 $12.110).
# Estas entidades son muy estrictas con tarifas; si no se cita la normativa
# SOAT exacta, ratifican la glosa.
_KEYWORDS_ASEGURADORAS_SOAT = (
    "SEGUROS",
    "COMPAÑIA DE SEGUROS",
    "COMPANIA DE SEGUROS",
    "BOLIVAR",
    "POSITIVA",
    "AXA",
    "MAPFRE",
    "MUNDIAL",
    "PREVISORA",
    "SURAMERICANA S.A.",
    "COLPATRIA",
    "ESTADO",
    "ALLIANZ",
    "LIBERTY",
    " SOAT",
    " ARL",
    "UVB",
    "UVT",  # sufijos tipicos en nombres de Excel
    "DIRECCION DE SANIDAD",  # Sanidad Militar/Policia = SOAT plus
    "DISPENSARIO MEDICO",
    "SANIDAD NAVAL",
    "SANIDAD AEREA",
)


def _es_aseguradora_soat(nombre: str) -> bool:
    """True si el nombre parece de aseguradora SOAT/ARL sin contrato pactado."""
    if not nombre:
        return False
    n = str(nombre).upper()
    return any(k in n for k in _KEYWORDS_ASEGURADORAS_SOAT)


def _extraer_nombre_entidad_real(texto: str) -> str:
    """Extrae el nombre de entidad de un texto que venga en formato
    "CÓDIGO - NOMBRE" (típico del Excel de recepción o de la hoja I/R).

    Ejemplo: "U220154 - COMPAÑIA MUNDIAL DE SEGUROS S.A.  SOAT UVB"
    → "COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB"
    """
    if not texto:
        return ""
    m = re.search(r"[A-Z]\d{5,8}\s*[-–—]\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9\.\s&/]+)", str(texto).upper())
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return ""


def _nombre_entidad_para_texto(eps: str, texto_contextual: str = "") -> str:
    """Sanitiza el nombre de EPS para uso en texto institucional.

    Casos como "OTRA / SIN DEFINIR" intentan primero extraer el nombre
    REAL del texto_contextual (ej. tabla_excel que trae la EPS del
    Excel: "U220154 - COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB").
    Si no hay nombre real, cae a "LA ENTIDAD PAGADORA" (genérico).
    """
    if not eps:
        e = ""
    else:
        e = str(eps).upper().strip()
    es_generica = (not e) or any(
        k in e for k in ("OTRA", "SIN DEFINIR", "SIN CONTRATO", "N/A", "DESCONOCID")
    )
    if es_generica:
        # Intentar extraer el nombre real del texto contextual
        nombre_real = _extraer_nombre_entidad_real(texto_contextual or "")
        if nombre_real:
            return f"LA ENTIDAD {nombre_real}"
        return "LA ENTIDAD PAGADORA"
    return f"LA ENTIDAD {e}"


def generar_texto_injustificada(
    eps: str, codigo: str = "", valor: str = "", texto_contextual: str = ""
) -> str:
    """Argumento fijo para glosas de tarifas SIN contrato pactado.

    NOTA (mayo 2026 - directiva Yesid): el nombre de la función se mantiene
    por compatibilidad pero el texto generado YA NO USA la palabra
    "injustificada/o/os/as" en NINGUNA forma. La apertura ahora es
    "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS…" (sin
    adjetivo). Esto es coherente con el sanitizer global del flujo
    analizar() que reemplaza cualquier "injustific*" por "improcedente".

    Estructura de 4 párrafos. Si la EPS es genérica ("OTRA / SIN DEFINIR"),
    se intenta extraer el nombre real del texto_contextual.
    """
    entidad = _nombre_entidad_para_texto(eps, texto_contextual=texto_contextual)
    codigo_str = codigo if codigo else "DE TARIFAS"
    valor_str = (
        valor
        if valor and valor.strip() not in ("$ 0.00", "$0.00", "$ 0", "")
        else "EL VALOR INDICADO EN EL EXPEDIENTE"
    )

    return (
        f"ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
        f"INTERPUESTA POR {entidad} BAJO EL CÓDIGO {codigo_str}, FACTURADA POR "
        f"{valor_str}. "
        f"LA OBJECIÓN NO SE AJUSTA AL MARCO CONTRACTUAL NI NORMATIVO POR LAS "
        f"SIGUIENTES RAZONES: EN PRIMER LUGAR, NO EXISTE CONTRATO PACTADO ENTRE "
        f"LAS PARTES QUE CONTEMPLE UNA TARIFA CONVENIDA DISTINTA A LA DEL MANUAL "
        f"SOAT, POR LO QUE LA FACTURACIÓN SE REALIZÓ BAJO TARIFA SOAT PLENA. "
        f"EN SEGUNDO LUGAR, NO ES ADMISIBLE APLICAR DESCUENTOS UNILATERALES SIN "
        f"SOPORTE CONTRACTUAL. EN TERCER LUGAR, LA GLOSA CARECE DE EVIDENCIA DE "
        f"UNA TARIFA DISTINTA QUE JUSTIFIQUE LA REDUCCIÓN APLICADA. "
        f"DE CONFORMIDAD CON LA CIRCULAR EXTERNA 047 DE 2025 DEL MINISTERIO DE "
        f"SALUD (MANUAL TARIFARIO SOAT 2026 INDEXADO A UVB — VALOR UVB 2026: $12.110) Y "
        f"EL DECRETO 780 DE 2016, EL MANUAL TARIFARIO SOAT RIGE SUPLETORIAMENTE A FALTA DE "
        f"CONTRATO. POR SU PARTE, EL ARTÍCULO 871 DEL CÓDIGO DE COMERCIO "
        f"CONSAGRA EL PRINCIPIO DE BUENA FE CONTRACTUAL, Y EL ARTÍCULO 177 DE "
        f"LA LEY 100 DE 1993 ESTABLECE EL DEBER DE LA ENTIDAD PAGADORA DE "
        f"RECONOCER LOS VALORES DEBIDAMENTE FACTURADOS POR LOS SERVICIOS "
        f"PRESTADOS. "
        f"EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO "
        f"DE LA GLOSA Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO CONFORME "
        f"AL MANUAL TARIFARIO SOAT. DE PERSISTIR LA OBJECIÓN, SE INVITA A MESA "
        f"DE CONCILIACIÓN DE AUDITORÍA (ART. 20 DEC. 4747/2007). "
        f"COMUNICACIONES: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
    )


class GlosaService:
    def __init__(
        self,
        groq_api_key: str = None,
        anthropic_api_key: str = None,
        primary_ai: str = "anthropic",
        anthropic_model: str = "claude-sonnet-4-6",
        groq_model: str = "openai/gpt-oss-120b",
        gemini_api_key: str = None,
        gemini_model: str = "gemini-2.0-flash",
        groq_model_fallback_1: str = "qwen/qwen3-32b",
        groq_model_fallback_2: str = "llama-3.3-70b-versatile",
    ):
        _timeout = httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=5.0)
        self.groq = AsyncGroq(api_key=groq_api_key, timeout=_timeout) if groq_api_key else None
        self.anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        # Jun-2026 (decisión Yesid): la cadena de DICTÁMENES queda en SOLO
        # Groq (primario, gratis/rápido) + Anthropic (calidad / casos
        # complejos). Gemini y OpenRouter salieron del dictamen — "no las
        # veo trabajando y de pago ya tenemos Claude". Si llega un
        # primary_ai legacy ("gemini"/"openrouter", p.ej. un secret viejo
        # de Fly), se normaliza a "groq" para no dejar el motor sin
        # proveedor primario válido.
        self.primary_ai = (primary_ai or "anthropic").lower()
        if self.primary_ai in ("gemini", "openrouter"):
            logger.warning(
                f"[IA] primary_ai={self.primary_ai!r} ya no genera dictámenes "
                "(proveedor retirado jun-2026). Normalizando a 'groq'."
            )
            self.primary_ai = "groq"
        self.anthropic_model = anthropic_model or "claude-sonnet-4-6"
        # Cadena de modelos DENTRO de Groq (decision 12-jun-2026, ver
        # app/core/config.py): gpt-oss-120b → qwen3-32b → llama-3.3-70b.
        # Si el primario falla (429/transitorio/deprecado) se prueba el
        # siguiente modelo Groq ANTES de saltar a Anthropic — ver
        # _modelos_groq() y _llamar_groq_con_retry().
        self.groq_model = groq_model or "openai/gpt-oss-120b"
        self.groq_model_fallback_1 = groq_model_fallback_1 or "qwen/qwen3-32b"
        self.groq_model_fallback_2 = groq_model_fallback_2 or "llama-3.3-70b-versatile"
        # Google Gemini se conserva ÚNICAMENTE para lectura de PDFs
        # escaneados: OCR (pdf_service.extraer_con_ocr) y la cadena
        # multimodal del pdf_fallback_patch (A=Anthropic → B=Gemini PDF →
        # C=Gemini Vision). NO participa en la generación de dictámenes
        # vía _llamar_ia.
        from app.services.gemini_service import GeminiService

        gem_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        self.gemini = (
            GeminiService(api_key=gem_key, default_model=gemini_model) if gem_key else None
        )
        self.gemini_model = gemini_model

    async def analizar(
        self,
        data: GlosaInput,
        contexto_pdf: str = "",
        contratos_db: dict = None,
        few_shots: list[str] = None,
        info_tarifa: dict = None,
        hint_gestor: str = "",
        pdfs_raw_para_multimodal: list[tuple[str, bytes]] = None,
    ) -> GlosaResult:
        # `hint_gestor` se inyecta como contexto adicional al few_shots
        # cuando viene del módulo memoria_gestor — lleva el estilo
        # personal de refinamiento del auditor logueado.
        if hint_gestor:
            if few_shots is None:
                few_shots = []
            few_shots = list(few_shots) + [hint_gestor]
        texto_base = str(data.tabla_excel).strip().upper()

        codigos_detectados = self._extraer_codigos_glosa(texto_base)
        codigo_det = codigos_detectados[0] if codigos_detectados else "N/A"
        if len(codigos_detectados) > 1:
            # Multi-código (jun-2026): antes se procesaba SOLO el primero y
            # el dictamen mezclaba familias sin declararlas. Con el flag ON
            # (default) cada código adicional recibe su propia sección de
            # argumentación — ver bloque "un dictamen por código" más abajo,
            # tras ensamblar el dictamen del principal.
            from app.services.multi_codigo import (
                MAX_CODIGOS_DICTAMEN,
                multi_codigo_habilitado,
            )

            if multi_codigo_habilitado():
                logger.info(
                    f"Multi-código detectado ({len(codigos_detectados)}): {codigos_detectados}. "
                    f"Se procesarán todos con un dictamen por código "
                    f"(máx {MAX_CODIGOS_DICTAMEN}; principal: {codigo_det})."
                )
            else:
                logger.warning(
                    f"Multi-código detectado ({len(codigos_detectados)}): {codigos_detectados}. "
                    f"Se procesa solo el primero ({codigo_det}) — MULTI_CODIGO_DICTAMENES=0."
                )
        prefijo = codigo_det[:2] if codigo_det and codigo_det != "N/A" else "XX"
        valor_raw = self._extraer_valor(texto_base)

        msg_tiempo, color_tiempo, dias = "Fechas no ingresadas", "bg-slate-500", 0
        if data.fecha_radicacion and data.fecha_recepcion:
            try:
                dias_calc = self._calcular_dias_habiles(
                    str(data.fecha_radicacion), str(data.fecha_recepcion)
                )
                if dias_calc is None:
                    # Fechas presentes pero imparseables: NO clasificar como
                    # "DENTRO DE TÉRMINOS" (antes dias=0 silencioso perdía la
                    # defensa RE9502 por extemporaneidad). El gestor debe
                    # verificar las fechas. Auditoría jun-2026, P1 #5.
                    msg_tiempo = "FECHAS NO VÁLIDAS — VERIFICAR RADICACIÓN/RECEPCIÓN"
                    color_tiempo = "bg-amber-500"
                else:
                    dias = dias_calc
                    # PLAZO LEGAL: 20 días hábiles para que la EPS formule glosa (Art. 57 Ley 1438/2011 + Dec. 4747/2007)
                    es_extemporanea = dias > DIAS_HABILES_LIMITE_EXTEMPORANEA
                    msg_tiempo = (
                        f"EXTEMPORÁNEA ({dias} DÍAS HÁBILES - LÍMITE: {DIAS_HABILES_LIMITE_EXTEMPORANEA})"
                        if es_extemporanea
                        else f"DENTRO DE TÉRMINOS ({dias} DÍAS HÁBILES)"
                    )
                    color_tiempo = "bg-red-600" if es_extemporanea else "bg-emerald-500"
            except Exception as e:
                logger.error(f"Error fechas: {e}")

        # CORRECCIÓN: inicializar tipo_glosa antes de usarlo para evitar UnboundLocalError
        tipo_glosa = self._determinar_tipo_glosa(prefijo, texto_base)

        es_extemporanea = dias > DIAS_HABILES_LIMITE_EXTEMPORANEA
        es_ratificacion = "RATIF" in str(data.etapa).upper()
        tiene_pdf = bool(contexto_pdf and len(contexto_pdf.strip()) > 0)
        es_urgencia = "URGENCIA" in texto_base or "URGENTE" in texto_base
        # Es tarifa SOLO si el prefijo del código es TA. FA=facturación,
        # SO=soportes, AU=autorización, CO=cobertura, etc. NO inferir
        # "tarifa" del texto libre porque genera falsos positivos (ej.
        # FA0801 cuyo motivo menciona "valores pactados" pero NO es TA).
        es_tarifa = prefijo == "TA"

        eps_key = str(data.eps).upper().replace(" / SIN DEFINIR", "").strip()
        tiene_contrato = eps_key in (contratos_db or {})

        argumento_fijo = None
        if es_ratificacion:
            argumento_fijo = TEXTO_RATIFICADA
            tipo_glosa = "RATIFICADA"
        elif es_extemporanea:
            argumento_fijo = generar_texto_extemporanea(dias)
            tipo_glosa = "EXTEMPORANEA"
        elif es_tarifa and _es_dispensario_medico(eps_key):
            # Override institucional (Yesid abr 2026, hasta nueva orden):
            # toda glosa TA* de Dispensario Médico Bucaramanga (DMBUG)
            # responde con el texto canónico que cita el contrato
            # 440-DIGSA/DMBUG-2025. NO se llama al motor IA — ahorra
            # tokens y garantiza consistencia jurídica entre todas las
            # glosas de este pagador.
            argumento_fijo = TEXTO_DMBUG_TARIFAS
            tipo_glosa = "TA_DMBUG_FIJO"
        elif es_tarifa and not tiene_contrato:
            # Pasamos texto_base como contexto — si eps_key es "OTRA / SIN DEFINIR",
            # la funcion extrae el nombre real del Excel (ej. COMPAÑIA MUNDIAL DE
            # SEGUROS S.A. SOAT UVB) y lo usa en el texto.
            argumento_fijo = generar_texto_injustificada(
                eps_key,
                codigo_det,
                valor_raw,
                texto_contextual=texto_base,
            )
            tipo_glosa = "TA_TARIFA"

        # Modo de respuesta explicito por concepto (Sprint 1):
        # Si el auditor marco "aceptar_total" o "aceptar_parcial", sobreescribe
        # el argumento con la plantilla correspondiente (RE9702 o RE9801).
        # El flujo por defecto "defender" mantiene el comportamiento previo.
        modo_resp = (getattr(data, "modo_respuesta", None) or "defender").lower()
        if modo_resp == "aceptar_total":
            argumento_fijo = generar_texto_aceptacion_total(
                codigo_glosa=codigo_det, valor=valor_raw, servicio=""
            )
            tipo_glosa = "ACEPTADA_TOTAL"
        elif modo_resp == "aceptar_parcial":
            val_obj_num = 0.0
            val_ace_num = float(getattr(data, "valor_aceptado_parcial", 0.0) or 0.0)
            try:
                import re as _rex

                # Remover decimales tipo .00 antes de extraer digitos para
                # que "$100.00" no se convierta en "10000" (concatenacion de
                # "100" + "00"). Los valores del Excel son enteros COP.
                sin_dec = _rex.sub(r"\.\d{1,2}(?=\s|$|[^\d])", "", str(valor_raw))
                numeros = _rex.findall(r"\d+", sin_dec)
                if numeros:
                    val_obj_num = float("".join(numeros))
            except Exception:
                pass
            argumento_fijo = generar_texto_aceptacion_parcial(
                codigo_glosa=codigo_det,
                valor_objetado=val_obj_num,
                valor_aceptado=val_ace_num,
                servicio="",
            )
            tipo_glosa = "ACEPTADA_PARCIAL"

        # Optimización #7: si hay match perfecto de tarifa pactada
        # (DEFENDER_TOTAL con valor_pactado > 0 y facturado ≈ pactado),
        # generar dictamen determinístico SIN llamar al LLM. Ahorra ~8k
        # tokens por glosa. Solo se activa si no hay ya un argumento_fijo
        # (extemporánea/ratificada/aceptada tienen prioridad).
        if argumento_fijo is None and es_tarifa and info_tarifa and info_tarifa.get("encontrada"):
            rec = info_tarifa.get("recomendacion") or {}
            pact = float(info_tarifa.get("valor_pactado_calc") or 0.0)
            fact = float(info_tarifa.get("valor_facturado") or 0.0)
            # Match perfecto: DEFENDER_TOTAL + valor_pactado real + fact ≈ pact
            if (
                rec.get("accion") == "DEFENDER_TOTAL"
                and pact > 0
                and abs(fact - pact) < max(1.0, pact * 0.005)
            ):
                val_obj_mt = 0.0
                try:
                    import re as _rem

                    sin_dec_m = _rem.sub(r"\.\d{1,2}(?=\s|$|[^\d])", "", str(valor_raw))
                    nums_m = _rem.findall(r"\d+", sin_dec_m)
                    if nums_m:
                        val_obj_mt = float("".join(nums_m))
                except Exception:
                    pass
                argumento_fijo = generar_texto_tarifa_match(
                    codigo_glosa=codigo_det,
                    valor_objetado=val_obj_mt,
                    info_tarifa=info_tarifa,
                )
                tipo_glosa = "TARIFA_MATCH_PERFECTO"
                logger.info(
                    f"[AHORRO-IA] Match perfecto detectado: cups={info_tarifa.get('tarifa', {}).get('codigo_cups')} "
                    f"pactado=${pact:,.0f} facturado=${fact:,.0f} — plantilla fija usada (0 tokens)"
                )

        # Selección RE según Manual Único (Res. 2284/2023) y práctica HUS:
        #   RE9702 → IPS acepta 100%
        #   RE9801 → IPS acepta parcial y subsana
        #   RE9901 → defensa estándar: IPS no acepta y subsana aportando
        #            soporte / referencia contractual. Es el código más
        #            común cuando hay contrato pactado y el HUS defiende
        #            la tarifa contractual.
        #   RE9502 → glosa extemporánea (aceptación tácita Art. 57 Ley 1438)
        #   RE9602 → glosa injustificada al 100% (IPS aporta evidencia
        #            de la injustificación). Aplica cuando NO hay contrato
        #            pactado y la defensa se apoya en SOAT pleno + ausencia
        #            de pacto distinto. Si hay contrato cargado, va RE9901.
        if modo_resp == "aceptar_total":
            cod_res, desc_res = "RE9702", "GLOSA ACEPTADA AL 100% POR EL PRESTADOR"
        elif modo_resp == "aceptar_parcial":
            cod_res, desc_res = "RE9801", "GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE"
        elif es_ratificacion:
            cod_res, desc_res = (
                "RE9901",
                "GLOSA RATIFICADA - SE MANTIENE RESPUESTA INICIAL, SE SOLICITA CONCILIACIÓN",
            )
        elif es_extemporanea:
            cod_res, desc_res = (
                "RE9502",
                "GLOSA NO PROCEDE - ACEPTACIÓN TÁCITA (Art. 57 Ley 1438/2011)",
            )
        elif es_tarifa and _es_dispensario_medico(eps_key):
            # Override DMBUG: contrato 440-DIGSA/DMBUG-2025 está vigente,
            # por lo que la respuesta es RE9901 (defensa con contrato),
            # NO RE9602 (injustificada). Aún si tiene_contrato es False
            # porque el eps_key viene con prefijo U220311.
            cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA - SUBSANADA EN SU TOTALIDAD"
        elif es_tarifa and not tiene_contrato:
            cod_res, desc_res = (
                "RE9602",
                "GLOSA INJUSTIFICADA - APORTA EVIDENCIA DE INJUSTIFICACIÓN",
            )
        else:
            cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA - SUBSANADA EN SU TOTALIDAD"

        plantilla = obtener_plantilla_por_codigo(codigo_det)
        usa_plantilla = plantilla is not None
        arg_limpio = ""
        normas_clave = ""
        modelo_usado = "desconocido"

        # Inicializar variables de decisión IA — pueden ser sobreescritas
        # por texto fijo (mapping abajo) o por XML extraído del LLM.
        accion_ia = ""
        valor_aceptar_ia = 0.0
        valor_defender_ia = 0.0

        if argumento_fijo:
            pac_ia = "N/A"
            # Mapeo fijo: el tipo de texto canónico determina la acción.
            _mapa_accion = {
                "RATIFICADA": "DEFENDER_TOTAL",
                "EXTEMPORANEA": "DEFENDER_TOTAL",
                "TARIFA_MATCH_PERFECTO": "DEFENDER_TOTAL",
                "ACEPTADA_TOTAL": "ACEPTAR_TOTAL",
                "ACEPTADA_PARCIAL": "ACEPTAR_PARCIAL",
            }
            accion_ia = _mapa_accion.get(tipo_glosa, "")
            try:
                from app.services.auto_pilot_decision import _parse_valor as _pval_vobj

                _vobj = _pval_vobj(valor_raw)
            except Exception:
                _vobj = 0.0
            if accion_ia == "DEFENDER_TOTAL":
                valor_defender_ia = _vobj
            elif accion_ia == "ACEPTAR_TOTAL":
                valor_aceptar_ia = _vobj
            # EXTEMPORANEA y ACEPTADA_* usan textos 100% fijos curados por el
            # equipo juridico — NO pasan por _suavizar_tono() porque ese
            # reemplaza frases como "SE EXIGE EL LEVANTAMIENTO" o "CARECE DE
            # TODO SUSTENTO LEGAL" que son intencionales en estos textos.
            # Las ratificadas tampoco deben tocarse (TEXTO_RATIFICADA es fijo).
            _saltar_suavizar = tipo_glosa in (
                "EXTEMPORANEA",
                "RATIFICADA",
                "ACEPTADA_TOTAL",
                "ACEPTADA_PARCIAL",
                "TARIFA_MATCH_PERFECTO",
            )
            arg_ia = argumento_fijo if _saltar_suavizar else _suavizar_tono(argumento_fijo)
            # Sanitizer: aplicar al camino de texto_fijo para garantizar que
            # ninguna plantilla hardcoded use "injustific*", EXCEPTO cuando el
            # codigo de respuesta es RE9602 (concepto canonico del catalogo).
            arg_ia = limpiar_palabra_injustificado(arg_ia, codigo_respuesta=cod_res)
            # Sanitizer cierre canónico: solo ratificadas/extemporáneas
            # llevan el "...10 días hábiles... mesa de conciliación...
            # CARTERA@HUS.GOV.CO". Cualquier otra defensa lo pierde.
            arg_ia = limpiar_cierre_extemporanea_indebido(
                arg_ia,
                es_ratificacion=es_ratificacion,
                es_extemporanea=es_extemporanea,
                codigo_respuesta=cod_res,
            )
            arg_limpio = arg_ia.replace("<br/>", " ").replace("*", "").replace("\n", " ")
            modelo_usado = "texto_fijo"
            servicio_ia = ""
            contrato_ia = ""
            tarifa_ia = ""
            normas_clave = ""
        elif usa_plantilla:
            pac_ia = "N/A (PLANTILLA)"
            arg_ia = _suavizar_tono(plantilla["plantilla"])
            arg_limpio = arg_ia.replace("<br/>", " ").replace("*", "").replace("\n", " ")
            modelo_usado = "plantilla"
            servicio_ia = ""
            contrato_ia = ""
            tarifa_ia = ""
            normas_clave = ""
        else:
            prefijo = tipo_glosa[:2].upper() if tipo_glosa else "FA"
            # R59 P3: si el gestor pidió 'auditoria_previa', usamos el
            # prompt neutral que NO redacta dictamen sino diagnóstico.
            # No depende del prefijo — el flujo de auditoría es uniforme
            # para todos los tipos de glosa.
            if modo_resp == "auditoria_previa":
                from app.services.glosa_ia_prompts import get_system_prompt_auditoria

                system_prompt = get_system_prompt_auditoria(eps=data.eps)
            else:
                system_prompt = get_system_prompt(prefijo=prefijo, eps=data.eps)
            # Fase 3: inyectar contexto de tarifa oficial si es TA con CUPS
            # conocido. Le da a la IA el valor EXACTO publicado (Res. 124/2026
            # HUS o Circular 047/2025 SOAT) para que arme un dictamen con
            # números duros, no con suposiciones.
            if prefijo == "TA":
                try:
                    import re as _re_ta
                    from app.services.tarifas_oficiales import (
                        contexto_tarifa_oficial,
                    )

                    m_cups = _re_ta.search(r"\b(\d{4,7}[A-Z]?\d*)\b", texto_base)
                    if m_cups:
                        ctx_oficial = contexto_tarifa_oficial(m_cups.group(1))
                        if ctx_oficial:
                            system_prompt += (
                                "\n\n═══ VALOR OFICIAL CONOCIDO DEL CUPS ═══\n"
                                + ctx_oficial
                                + "\n═══════════════════════════════════════\n"
                                "USA ESTE VALOR EXACTO EN EL DICTAMEN. Cita la "
                                "resolución en el argumento. No inventes cifras."
                            )
                except Exception:
                    pass
            # Detectar si es aseguradora SOAT (sin contrato o con contrato UVB)
            # para que el prompt IA agregue obligatoriamente la cita al Manual
            # Tarifario SOAT vigente. Revisa eps + texto_base (por si la EPS
            # es "OTRA / SIN DEFINIR" pero el Excel trae aseguradora real).
            es_asegura_soat = _es_aseguradora_soat(str(data.eps)) or _es_aseguradora_soat(
                texto_base
            )
            if es_asegura_soat:
                nombre_real = _extraer_nombre_entidad_real(texto_base) or str(data.eps)
                hint_aseguradora = (
                    "\n\n═══════════════════════════════════════════════════════\n"
                    "⚠ ALERTA CRÍTICA: ASEGURADORA SOAT / ARL / PÓLIZA SIN CONTRATO\n"
                    f"Entidad detectada: {nombre_real}\n"
                    "═══════════════════════════════════════════════════════\n"
                    "Esta entidad paga bajo MANUAL TARIFARIO SOAT VIGENTE. DEBES:\n"
                    "1. Citar EXPLÍCITAMENTE la Resolución 054 de 2026 (vigente,\n"
                    "   tarifas SOAT 2026) y el Decreto 2423 de 1996 (manual base).\n"
                    "2. Argumentar que NO HAY CONTRATO PACTADO, por lo que rige\n"
                    "   SOAT PLENO y no es admisible descontar UVB/UVT sin soporte.\n"
                    "3. Citar Art. 177 Ley 100/1993 (deber de reconocimiento).\n"
                    "4. NO aceptar descuentos unilaterales — Art. 871 C.Comercio\n"
                    "   exige consentimiento mutuo para modificar tarifas.\n"
                    "5. Para régimen especial FF.MM./Policía: Decreto 1795/2000.\n"
                    "   Para FOMAG/PPL: Decreto 1398/2020.\n"
                    "6. Usar el nombre EXACTO de la entidad en la respuesta\n"
                    f'   ("{nombre_real}"), no genéricos como "LA ENTIDAD PAGADORA".\n'
                    "═══════════════════════════════════════════════════════"
                )
                system_prompt = system_prompt + hint_aseguradora
                logger.info(f"[ASEGURADORA SOAT] detectada: {nombre_real} — prompt reforzado")
            # Inyectar few-shots de plantillas gold (si hay) al final del system
            if few_shots:
                bloque_ejemplos = "\n\nEJEMPLOS DE RESPUESTAS GANADORAS PREVIAS (usa el MISMO estilo, tono y nivel de detalle):\n"
                for i, ej in enumerate(few_shots, start=1):
                    # Recortar ejemplos largos para no desbordar ventana
                    ej_corto = ej[:1200] + ("…" if len(ej) > 1200 else "")
                    bloque_ejemplos += f"\n--- EJEMPLO #{i} (respuesta que logró levantar la glosa) ---\n{ej_corto}\n"
                bloque_ejemplos += "\n--- FIN EJEMPLOS ---\n\nGenera una respuesta NUEVA para el caso actual inspirándote en el estilo anterior, adaptando a los datos específicos. No copies literal."
                system_prompt = system_prompt + bloque_ejemplos
                logger.info(f"Prompt enriquecido con {len(few_shots)} plantilla(s) gold")
            # CUPS verificado: extraer SOLO del texto de la glosa (no del PDF
            # que trae números de ingreso/HC/folio que no son CUPS).
            # Ronda 47 fix: aceptar códigos alfanuméricos con sufijos tipo
            # '39147B-18', '372301H', 'FMQ6296', '19914262-04' (CUM medicamentos).
            cups_verificado = ""
            try:
                from app.main import _extraer_cups_servicio as _extcups

                _c, _ = _extcups(texto_base, "")
                cups_verificado = _c or ""
            except Exception:
                # Fallback al regex viejo (solo dígitos) — no bloquear si hay
                # un problema de import circular durante startup.
                # Ronda 2 (12-jun-2026, fix #8): el fallback aceptaba fechas
                # ("CUPS 2026-04" de la fecha 2026-04-15) y facturas ("CUPS
                # HUS0000522871") como candidatos — mismas exclusiones del
                # extractor principal vía es_cups_descartable.
                try:
                    from app.services.contexto_contractual_enriquecido import (
                        es_cups_descartable as _cups_desc,
                    )
                except Exception:

                    def _cups_desc(c, t=""):
                        return False

                for _m_cups in re.finditer(
                    r"(?:^|\s|[-·,])\s*([A-Z]{0,3}\d{4,8}[A-Z]?\d{0,2}(?:-\d{1,3})?)\s*(?:[-·,]|\s+[A-ZÁÉÍÓÚÑ])",
                    texto_base,
                ):
                    if not _cups_desc(_m_cups.group(1), texto_base):
                        cups_verificado = _m_cups.group(1)
                        break
                if not cups_verificado:
                    for _m2 in re.finditer(r"\b(\d{5,6}[A-Z]?\d{0,2}(?:-\d{1,3})?)\b", texto_base):
                        if not _cups_desc(_m2.group(1), texto_base):
                            cups_verificado = _m2.group(1)
                            break

            # Extraer valor facturado/pactado de info_tarifa cuando esté
            # disponible. Es la única forma fiable de distinguir el
            # FACTURADO ($247.663 ej.) del OBJETADO ($168.563 ej.). Si no
            # hay info_tarifa, ambos quedan en None y el prompt se redacta
            # con el patrón "OBJETA $X" sin mencionar facturado.
            _val_fact_str: Optional[str] = None
            _val_pact_str: Optional[str] = None
            try:
                if info_tarifa and info_tarifa.get("encontrada"):
                    _vf = float(info_tarifa.get("valor_facturado") or 0.0)
                    _vp = float(info_tarifa.get("valor_pactado_calc") or 0.0)
                    if _vf > 0:
                        _val_fact_str = f"${_vf:,.0f}".replace(",", ".")
                    if _vp > 0:
                        _val_pact_str = f"${_vp:,.0f}".replace(",", ".")
            except Exception:
                pass

            # CLAUSULAS LITERALES del contrato firmado con esta EPS — extraidas
            # del PDF via /contratos/extraer-clausulas-pdf. Si la EPS no tiene
            # contrato cargado, devuelve [] y el prompt no agrega bloque.
            _clausulas_contrato = []
            try:
                from app.services.glosa_ia_prompts import get_clausulas_para_glosa

                _clausulas_contrato = get_clausulas_para_glosa(
                    eps=str(data.eps or ""),
                    codigo_glosa=codigo_det,
                    max_clausulas=5,
                )
                if _clausulas_contrato:
                    logger.info(
                        f"[CLAUSULAS-CONTRATO] {len(_clausulas_contrato)} clausulas "
                        f"inyectadas para EPS={data.eps} codigo={codigo_det}"
                    )
            except Exception as _e_cc:
                logger.debug(f"[CLAUSULAS-CONTRATO] no disponibles: {_e_cc}")

            user_prompt = build_user_prompt(
                texto_glosa=texto_base,
                contexto_pdf=contexto_pdf,
                codigo=codigo_det,
                eps=data.eps,
                numero_factura=data.numero_factura,
                numero_radicado=data.numero_radicado,
                dias_habiles=dias,
                es_extemporanea=es_extemporanea,
                cups_verificado=cups_verificado or None,
                valor_objetado=valor_raw,
                valor_facturado=_val_fact_str,
                valor_pactado=_val_pact_str,
                tono=getattr(data, "tono", "conciliador") or "conciliador",
                clausulas_contrato=_clausulas_contrato,
            )

            # ═══════════════════════════════════════════════════════════
            #  Extemporaneidad de la RATIFICACIÓN (12-jun-2026, ronda 2 —
            #  fix #5). Evidencia: "Fecha radicación: 2026-03-01. Fecha
            #  recepción ratificación: 2026-05-30" (~62 días hábiles) y el
            #  dictamen ni lo mencionó. El texto_fijo de BD solo cubre la
            #  glosa INICIAL; estas fechas vienen EN EL TEXTO. Si el par
            #  radicación → recepción-de-ratificación excede 30 días
            #  hábiles (Art. 57 Ley 1438/2011), la defensa PROCESAL va
            #  PRIMERO — se inyecta como bloque prioritario al prompt.
            #  NO toca la lógica texto_fijo existente.
            # ═══════════════════════════════════════════════════════════
            try:
                _fechas_txt = detectar_fechas_en_texto(texto_base)
                _f_rad_txt = _fechas_txt.get("fecha_radicacion")
                _f_rat_txt = _fechas_txt.get("fecha_ratificacion")
                if _f_rad_txt and _f_rat_txt:
                    _dias_rat = self._calcular_dias_habiles(_f_rad_txt, _f_rat_txt)
                    if _dias_rat is not None and _dias_rat > DIAS_HABILES_LIMITE_RATIFICACION:
                        # Ronda 7 (16-jun-2026 — fix O): el bloque procesal
                        # también se PREPENDE para que el modelo abra con
                        # la extemporaneidad ANTES del fondo.
                        _bloque_ext = (
                            "═══════════════ INSTRUCCIÓN PRIORITARIA #2 — DEFENSA PROCESAL "
                            "═══════════════\n"
                            "[EXTEMPORANEIDAD DETECTADA — ARGUMENTO PROCESAL OBLIGATORIO]\n"
                            f"La ratificación fue notificada {_dias_rat} días hábiles "
                            f"después de la radicación (radicación {_f_rad_txt} → "
                            f"recepción de la ratificación {_f_rat_txt}), excediendo el "
                            "término del Art. 57 de la Ley 1438 de 2011 (10 días hábiles "
                            "para respuesta).\n\n"
                            "OBLIGATORIO — esta defensa PROCESAL va PRIMERO: abre el "
                            "dictamen invocando la extemporaneidad de la ratificación "
                            "ANTES de cualquier defensa de fondo, y cita las dos fechas "
                            f"textualmente como evidencia ({_f_rad_txt} y {_f_rat_txt}).\n"
                            "═══════════════════════════════════════════════════════════"
                            "════════════════\n\n"
                        )
                        user_prompt = _bloque_ext + user_prompt
                        logger.info(
                            f"[EXTEMP-RATIFICACION] {_dias_rat} días hábiles entre "
                            f"radicación ({_f_rad_txt}) y recepción de ratificación "
                            f"({_f_rat_txt}) — bloque PREPENDIDO al prompt (prioritario #2)."
                        )
            except Exception as _e_ext_rat:
                logger.debug(f"[EXTEMP-RATIFICACION] detector no aplicado: {_e_ext_rat}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 5 (16-jun-2026) — Citas inducidas por la EPS.
            #  Evidencia caso 3 (Sanitas): la EPS apoyaba la glosa en
            #  "Sentencia C-313 de 2014 que ... 'establece que las IPS
            #  no podrán cobrar servicios complementarios...'" — cita
            #  ATRIBUIDA con texto inventado. El dictamen NI desvirtuó
            #  la cita NI la copió: simplemente la ignoró, argumentando
            #  por el otro lado. El gestor humano queda con la duda. Si
            #  detectamos una cita entrecomillada atribuida a una norma
            #  o sentencia DENTRO del texto de la glosa, inyectamos una
            #  instrucción prioritaria: DESVIRTUARLA EXPLÍCITAMENTE al
            #  inicio del dictamen.
            # ═══════════════════════════════════════════════════════════
            try:
                _citas_eps = _extraer_citas_inducidas_eps(texto_base)
                if _citas_eps:
                    # Ronda 7 (16-jun-2026 — fix O): el bloque iba al FINAL
                    # del prompt y el modelo lo ignoraba (evidencia caso 12
                    # Compensar — NOM-035/ISO 9001 inducidas no desvirtuadas).
                    # Ahora se PREPENDE con encabezado imperativo numerado;
                    # el modelo lo lee ANTES de cualquier otro contexto.
                    bloque_citas = (
                        "═══════════════ INSTRUCCIÓN PRIORITARIA #1 — LEE Y APLICA "
                        "ANTES DE REDACTAR ═══════════════\n"
                        "[CITAS INDUCIDAS POR LA EPS — DESVIRTUAR EN EL PRIMER PÁRRAFO]\n"
                        "La EPS apoya su glosa en citas atribuidas a normas o estándares "
                        "que NO necesariamente existen ni dicen lo que ella afirma. Algunas "
                        "(NOM mexicana, ISO, IEC, IEEE, normas internacionales) NO son "
                        "vinculantes en Colombia. Otras pueden ser sentencias o "
                        "resoluciones inexistentes en el corpus colombiano.\n\n"
                        "OBLIGATORIO — el PRIMER PÁRRAFO del dictamen DEBE:\n"
                        "  (a) Citar TEXTUALMENTE la cita atribuida por la EPS (señalar "
                        "norma y supuesto contenido).\n"
                        "  (b) Desvirtuarla explícitamente — por inexistencia, por no "
                        "aplicabilidad territorial (extranjera), o por tergiversación de "
                        "su texto real.\n"
                        "  (c) Solo después, exponer la defensa de fondo.\n\n"
                        "CITAS DETECTADAS A DESVIRTUAR:\n"
                    )
                    for i, c in enumerate(_citas_eps[:3], 1):
                        bloque_citas += f"  {i}. {c}\n"
                    bloque_citas += (
                        "═══════════════════════════════════════════════════════════════"
                        "════════════════\n\n"
                    )
                    user_prompt = bloque_citas + user_prompt
                    logger.info(
                        f"[CITA-INDUCIDA] {len(_citas_eps)} cita(s) atribuida(s) por la "
                        "EPS PREPENDIDAS al prompt (instrucción prioritaria #1)."
                    )
            except Exception as _e_ci:
                logger.debug(f"[CITA-INDUCIDA] detector no aplicado: {_e_ci}")

            # Multi-agent foundation (env var MULTI_AGENT_HABILITADO=1):
            # ejecuta el Auditor Agent ANTES de la IA principal para
            # producir hallazgos estructurados (JSON con fortalezas,
            # debilidades, soportes faltantes, recomendación). Los
            # inyectamos como bloque adicional al user_prompt para que
            # la IA principal redacte con ese contexto verificado.
            # Si el agente falla (timeout, JSON inválido, etc.), seguimos
            # sin él — nunca rompemos el análisis para el usuario.
            try:
                from app.services.multi_agent import (
                    multi_agent_habilitado,
                    ejecutar_auditor,
                )

                if multi_agent_habilitado() and self.anthropic_key:
                    _audit_result = await ejecutar_auditor(
                        texto_glosa=texto_base,
                        eps=str(data.eps or ""),
                        codigo=codigo_det,
                        contexto_pdf=contexto_pdf,
                        valor_objetado=valor_raw,
                        valor_facturado=_val_fact_str or "",
                        valor_pactado=_val_pact_str or "",
                        api_key=self.anthropic_key,
                        modelo=self.anthropic_model,
                    )
                    if _audit_result and _audit_result.get("json"):
                        import json as _json

                        hallazgos_str = _json.dumps(
                            _audit_result["json"], ensure_ascii=False, indent=2
                        )[:4000]
                        user_prompt += (
                            "\n\n═══ BLOQUE EXTRA: HALLAZGOS DEL AUDITOR PRE-IA ═══\n"
                            "(JSON estructurado producido por el Auditor Agent — "
                            "úsalo para apoyar tu argumentación, citar evidencia y "
                            "decidir el tono. NO repitas el JSON en tu respuesta.)\n\n"
                            f"{hallazgos_str}\n"
                        )
                        logger.info("[MULTI-AGENT] Auditor inyectó hallazgos en el prompt")
            except Exception as _e_ma:
                logger.debug(f"[MULTI-AGENT] Auditor falló: {_e_ma}")

            # Si hay tarifa pactada específica encontrada en el catálogo del
            # cliente (tarifas_contratadas), inyectar los datos reales al
            # user prompt para que la IA NO use el "tarifa genérica del contrato"
            # del get_contrato(). Esto evita incoherencias tipo
            # "contrato dice SOAT -5%" cuando el catálogo carga modalidad
            # PROPIAS con valor fijo $254.500 para este CUPS específico.
            if info_tarifa and info_tarifa.get("encontrada"):
                t = info_tarifa.get("tarifa") or {}
                rec = info_tarifa.get("recomendacion") or {}
                val_pact = info_tarifa.get("valor_pactado_calc") or 0.0
                val_fact = info_tarifa.get("valor_facturado") or 0.0
                val_rec = info_tarifa.get("valor_reconocido") or 0.0
                modalidad_real = t.get("modalidad") or ""
                contrato_real = t.get("contrato_numero") or ""
                cups_real = t.get("codigo_cups") or cups_verificado or ""
                tipo_t = t.get("tipo_tarifa", "VALOR_FIJO")
                if tipo_t == "SOAT_PORCENTAJE":
                    factor_t = float(t.get("factor_ajuste") or 0.0)
                    signo = "+" if factor_t > 0 else ""
                    pact_txt = f"SOAT {signo}{factor_t:.0f}%"
                else:
                    pact_txt = f"${val_pact:,.0f}"
                bloque_tarifa = (
                    "\n═══ BLOQUE EXTRA: TARIFA ESPECÍFICA DEL CUPS (autoritativa) ═══\n"
                    "El catálogo contractual cargado en el sistema tiene el valor\n"
                    f"pactado para este CUPS EXACTO. USA ESTOS DATOS, NO otros:\n"
                    f"  • CUPS contractual : {cups_real}\n"
                    f"  • Modalidad real   : {modalidad_real}\n"
                    f"  • Tarifa pactada   : {pact_txt}\n"
                    f"  • Contrato         : {contrato_real}\n"
                    f"  • Valor facturado HUS: ${val_fact:,.0f}\n"
                    f"  • Valor reconocido EPS: ${val_rec:,.0f}\n"
                    f"  • Recomendación sistema: {rec.get('titulo', '')}\n\n"
                    "REGLAS OBLIGATORIAS:\n"
                    "  1. Cita SIEMPRE el contrato y la modalidad REALES del catálogo,\n"
                    "     NO los genéricos de la ficha EPS global.\n"
                    "  2. Si la modalidad contiene 'PROPIA', 'PROPIAS', 'MANUAL HUS',\n"
                    "     'INSTITUCIONAL' o no dice 'SOAT': la tarifa es PROPIA de la\n"
                    "     ESE HUS (Res. 054/2026 + 124/2026 HUS, SMDLV × factor).\n"
                    "     En este caso NO digas 'SOAT/SMLV -20%' ni menciones\n"
                    "     descuento SOAT — es una tarifa propia institucional fija.\n"
                    "  3. Si la modalidad contiene 'SOAT' o 'UVB': cita la Circular\n"
                    "     047/2025 MinSalud + UVB 2026 $12.110.\n"
                    "  4. Usa el VALOR facturado y reconocido EXACTOS de arriba.\n"
                    "  5. Si tarifa pactada > valor facturado: la glosa es\n"
                    "     IMPROCEDENTE (facturamos por DEBAJO de lo pactado).\n"
                )
                user_prompt = user_prompt + bloque_tarifa

            # Ronda 6: agregar bloque multi-agente (Jurídico + Clínico +
            # Tarifario + Conciliador) al user_prompt. Les da a la IA
            # inputs curados por cada especialidad antes de redactar.
            try:
                from app.services.multi_agente import orquestar_dictamen

                _mod_agente = ""
                _fac_agente = 0.0
                _pact_agente = 0.0
                _tipo_t_agente = "VALOR_FIJO"
                _fact_agente = 0.0
                _rec_agente = 0.0
                if info_tarifa and info_tarifa.get("encontrada"):
                    _t = info_tarifa.get("tarifa") or {}
                    _mod_agente = _t.get("modalidad") or ""
                    _fac_agente = float(_t.get("factor_ajuste") or 0.0)
                    _pact_agente = float(info_tarifa.get("valor_pactado_calc") or 0.0)
                    _tipo_t_agente = _t.get("tipo_tarifa", "VALOR_FIJO")
                    _fact_agente = float(info_tarifa.get("valor_facturado") or 0.0)
                    _rec_agente = float(info_tarifa.get("valor_reconocido") or 0.0)
                bloque_agentes = orquestar_dictamen(
                    codigo_glosa=codigo_det,
                    eps=str(data.eps),
                    cups=cups_verificado or "",
                    servicio="",
                    etapa=str(data.etapa or "Inicial"),
                    tono=getattr(data, "tono", "conciliador") or "conciliador",
                    modalidad=_mod_agente,
                    factor_ajuste=_fac_agente,
                    valor_pactado=_pact_agente,
                    tipo_tarifa=_tipo_t_agente,
                    valor_facturado=_fact_agente,
                    valor_reconocido=_rec_agente,
                )
                if bloque_agentes:
                    user_prompt = user_prompt + bloque_agentes
            except Exception as _e:
                logger.debug(f"Multi-agente no inyectado (se ignora): {_e}")

            # ═══════════════════════════════════════════════════════════
            #  R-CEREBRO #2: Few-shot dinámico con dictámenes ganadores
            #  Inyecta 1-2 ejemplos GOLD (par eps+código que ya ganaron)
            #  para que el LLM aprenda del estilo que funcionó antes.
            # ═══════════════════════════════════════════════════════════
            _ejemplos_gold: list[dict] = []  # disponibles para detector copia
            try:
                from app.database import SessionLocal
                from app.services.few_shot_gold import (
                    bloque_few_shot_para_prompt,
                    obtener_ejemplos_gold,
                )

                _db_fs = SessionLocal()
                try:
                    _ejemplos_gold = obtener_ejemplos_gold(
                        _db_fs,
                        str(data.eps),
                        codigo_det,
                    )
                finally:
                    _db_fs.close()
                bloque_fs = bloque_few_shot_para_prompt(_ejemplos_gold)
                if bloque_fs:
                    user_prompt = user_prompt + bloque_fs
            except Exception as _e:
                logger.debug(f"Few-shot Gold no inyectado: {_e}")

            # ═══════════════════════════════════════════════════════════
            #  R-CEREBRO #6: Análisis del motivo EPS — puntos a refutar
            #  Parsea el texto de la glosa para extraer qué dice la EPS
            #  (valor reconocido, descuento, soportes faltantes, etc.)
            #  y pasarle al LLM una checklist explícita de qué atacar.
            # ═══════════════════════════════════════════════════════════
            try:
                from app.services.analizador_motivo_eps import (
                    construir_bloque_motivo_eps,
                )

                bloque_motivo = construir_bloque_motivo_eps(texto_base)
                if bloque_motivo:
                    user_prompt = user_prompt + bloque_motivo
            except Exception as _e:
                logger.debug(f"Análisis motivo EPS no inyectado: {_e}")

            # ═══════════════════════════════════════════════════════════
            #  R-CEREBRO #3: Calibración por dificultad histórica
            #  Si el par tiene tasa ≥70% → tono confiado / si ≤30% →
            #  blindaje reforzado / si en medio → estándar.
            # ═══════════════════════════════════════════════════════════
            try:
                from app.database import SessionLocal
                from app.services.calibracion_dificultad import (
                    construir_bloque_calibracion,
                )

                _db_cal = SessionLocal()
                try:
                    bloque_cal = construir_bloque_calibracion(
                        _db_cal,
                        str(data.eps),
                        codigo_det,
                    )
                finally:
                    _db_cal.close()
                if bloque_cal:
                    user_prompt = user_prompt + bloque_cal
            except Exception as _e:
                logger.debug(f"Calibración no inyectada: {_e}")

            # ═══════════════════════════════════════════════════════════
            #  R-CEREBRO #5: Ruteo dinámico Sonnet → Opus
            #  Para casos de ALTA complejidad (puntaje >= 6 ya marca
            #  "complejo", aquí endurecemos: solo si valor >= 10M Y
            #  hay 2+ PDFs) usamos Opus 4.7 que rinde mejor en tareas
            #  jurídicas largas.
            # ═══════════════════════════════════════════════════════════
            #  Routing en 3 niveles para optimizar costo:
            #    HAIKU  — casos simples / valor bajo / sin PDF / glosa
            #             corta. ~20× más barato que Sonnet.
            #    SONNET — caso por defecto.
            #    OPUS   — alta complejidad: valor>=10M + 2+ PDFs.
            #
            #  IMPORTANTE: el ruteo SOLO aplica cuando primary_ai usa
            #  Anthropic. Si el usuario eligió 'groq' como primary_ai,
            #  NO debemos forzar Anthropic — eso ignora la decisión
            #  deliberada (etapa testing, ahorrar tokens).
            _modelo_override = None
            _saltar_routing = self.primary_ai == "groq"
            try:
                if _saltar_routing:
                    logger.info(
                        f"[ROUTING-IA] SKIP — primary_ai={self.primary_ai} "
                        f"(usuario elige no usar Anthropic). El override Haiku/Opus "
                        f"solo aplica cuando primary_ai=anthropic."
                    )
                else:
                    # Usa el parser robusto que respeta formato colombiano
                    # ("7.700,00" = 7700, no 770000 como hacía el regex viejo).
                    # Bug detectado 12-may-2026: Sonnet se activaba para casos de
                    # $7.700 porque el parser interpretaba mal los puntos de miles.
                    from app.services.auto_pilot_decision import _parse_valor as _pval_route

                    _valor_num_route = int(_pval_route(valor_raw)) if valor_raw else 0
                    _num_pdfs_route = (contexto_pdf or "").count("═══ DOCUMENTO:")
                    _len_glosa_route = len(str(texto_base or ""))
                    _len_pdf_route = len(str(contexto_pdf or ""))

                    # OPUS: valor alto + multi-PDF
                    if _valor_num_route >= 10_000_000 and _num_pdfs_route >= 2:
                        _modelo_override = "claude-opus-4-7"
                        logger.info(
                            "[ROUTING-IA] OPUS — "
                            f"valor=${_valor_num_route:,} pdfs={_num_pdfs_route}"
                        )
                    # HAIKU: caso liviano. Reduce ~75% el costo y conserva
                    # calidad porque el cerebro pre-IA ya hizo el trabajo
                    # duro (auditoría + bloque excedente + checklist).
                    elif (
                        _valor_num_route < 500_000
                        and _num_pdfs_route <= 1
                        and _len_pdf_route < 5_000
                        and _len_glosa_route < 800
                    ):
                        _modelo_override = "claude-haiku-4-5-20251001"
                        logger.info(
                            "[ROUTING-IA] HAIKU — caso liviano "
                            f"(valor=${_valor_num_route:,}, "
                            f"pdfs={_num_pdfs_route}, "
                            f"texto={_len_glosa_route}c). "
                            "Ahorro ~75% vs Sonnet."
                        )
            except Exception:
                pass

            # ═══════════════════════════════════════════════════════════
            #  R-CEREBRO #10: Skip Claude (dictamen directo sin tokens).
            #  Si la pre-auditoría ya da veredicto contundente
            #  (score >= 70, DEFENDER_FUERTE, datos completos, sin
            #  excedente facturado), emitimos el dictamen con plantilla
            #  curada que cumple todas las reglas estructurales.
            #  Costo: $0. Latencia: ~50ms vs ~25s del LLM.
            # ═══════════════════════════════════════════════════════════
            res_ia = None
            modelo_usado = None
            try:
                from app.services.auditor_glosa import auditar
                from app.services.dictamen_directo import (
                    puede_emitir_directo,
                    generar_dictamen_directo,
                )

                _pact_num = 0.0
                _fact_num = 0.0
                if info_tarifa and info_tarifa.get("encontrada"):
                    _pact_num = float(info_tarifa.get("valor_pactado_calc") or 0.0)
                    _fact_num = float(info_tarifa.get("valor_facturado") or 0.0)
                _obj_num = 0.0
                if valor_raw:
                    from app.services.auto_pilot_decision import _parse_valor as _pval_obj

                    _obj_num = _pval_obj(valor_raw)
                _aud = auditar(
                    texto_base or "",
                    eps=str(data.eps),
                    codigo=codigo_det,
                    cups=cups_verificado,
                    tiene_contrato=tiene_contrato,
                    valor_facturado=_fact_num,
                    valor_pactado=_pact_num,
                    valor_objetado=_obj_num,
                    contexto_pdf=contexto_pdf or "",
                )
                _num_contrato_real = ""
                try:
                    from app.services.glosa_ia_prompts import get_contrato

                    _ctr = get_contrato(str(data.eps))
                    _num_contrato_real = _ctr.get("numero", "") if _ctr else ""
                except Exception:
                    pass
                # Si hay tarifa exacta del catálogo, usar ese contrato.
                if info_tarifa and info_tarifa.get("encontrada") and info_tarifa.get("tarifa"):
                    _ttar = info_tarifa.get("tarifa")
                    _ctr_cat = getattr(_ttar, "contrato_numero", None) or (
                        _ttar.get("contrato_numero") if isinstance(_ttar, dict) else None
                    )
                    if _ctr_cat:
                        _num_contrato_real = _ctr_cat

                if puede_emitir_directo(
                    _aud,
                    codigo=codigo_det,
                    eps=str(data.eps),
                    cups=cups_verificado,
                    valor_objetado=_obj_num,
                    valor_facturado=_fact_num,
                    valor_pactado=_pact_num,
                    tiene_contrato=tiene_contrato,
                    numero_contrato=_num_contrato_real,
                ):
                    _xml_directo = generar_dictamen_directo(
                        _aud,
                        codigo=codigo_det,
                        eps=str(data.eps),
                        cups=cups_verificado or "",
                        servicio=getattr(data, "servicio_descripcion", "") or "",
                        valor_objetado=_obj_num,
                        valor_facturado=_fact_num,
                        valor_pactado=_pact_num,
                        numero_contrato=_num_contrato_real,
                    )
                    if _xml_directo:
                        res_ia = _xml_directo
                        modelo_usado = "directo_auditor"
                        logger.info(
                            "[SKIP-CLAUDE] Dictamen emitido directamente "
                            f"sin LLM. score={_aud['score_evidencia']} "
                            f"hallazgos={_aud['n_hallazgos_alta']} "
                            f"ahorro=$~0.05 latencia=<100ms"
                        )
            except Exception as _e_dir:
                logger.debug(f"[SKIP-CLAUDE] Falló: {_e_dir}")
                res_ia = None

            # True cuando el dictamen final salió del Quality Gate (que ya
            # post-validó y regeneró hasta 3 veces). En ese caso el bloque
            # R-CEREBRO legacy de más abajo se salta — correr ambos duplicaba
            # hasta 2 llamadas LLM extra por glosa y podía producir veredictos
            # contradictorios (auditoría jun-2026, P1 #3).
            _dictamen_via_qg = False

            # Si NO se emitió directamente, llamar al LLM como siempre.
            if not res_ia:
                # Orden de preferencia para invocar al LLM:
                #   1. Multi-modal: si data.usar_pdf_nativo_soportes=True
                #      Y hay PDFs adjuntos, mandar PDFs binarios a Claude.
                #   2. Tool Use: si env var TOOL_USE_HABILITADO=1, Claude
                #      decide qué herramientas llamar (clausula, tarifa,
                #      norma, precedente).
                #   3. Clásico: prompt monolítico con todo inyectado.
                # Si 1 o 2 fallan, cascada al siguiente nivel; nunca
                # romper el análisis para el usuario final.
                _intento_ok = False

                # Path 1: Multi-modal soportes. La cadena de fallback que
                # PRESERVA los PDFs en cada nivel vive en
                # pdf_fallback_patch.py (parche aplicado al cargar los
                # routers): A=Anthropic PDF nativo → B=Gemini PDF nativo →
                # C=Gemini Vision con imágenes. Ese es el ÚNICO lugar donde
                # Gemini sigue tocando el dictamen — como lector de PDFs
                # escaneados cuando Anthropic falla (decisión jun-2026:
                # Gemini fuera del dictamen de texto; los duplicados B/C
                # inline que vivían aquí se eliminaron porque el parche ya
                # hacía la misma cadena y se reintentaba Gemini dos veces).
                # Si la cadena completa falla, caemos a los paths de texto
                # (Tool Use / clásico) con el contexto OCR ya extraído.
                _quiere_multimodal = (
                    bool(getattr(data, "usar_pdf_nativo_soportes", False))
                    and pdfs_raw_para_multimodal
                )
                if _quiere_multimodal:
                    try:
                        res_ia, modelo_usado = await self._llamar_anthropic_multimodal(
                            system_prompt,
                            user_prompt,
                            pdfs_raw_para_multimodal,
                        )
                        _intento_ok = True
                    except Exception as _e_mm:
                        logger.warning(
                            f"[MULTIMODAL] Cadena PDF agotada: {_e_mm}. Cae a texto plano."
                        )

                # Path 2: Tool Use opt-in vía env var
                if not _intento_ok:
                    try:
                        from app.services.ia_tools import tool_use_habilitado

                        if tool_use_habilitado():
                            try:
                                res_ia, modelo_usado = await self._llamar_anthropic_con_tools(
                                    system_prompt,
                                    user_prompt,
                                    modelo_override=_modelo_override,
                                )
                                _intento_ok = True
                            except Exception as _e_tools:
                                logger.warning(f"[TOOL-USE] Falló, fallback a clásico: {_e_tools}")
                    except Exception:
                        pass

                # Path 3: clásico (con caché + fallback a Groq)
                if not _intento_ok:
                    # Quality Gate: cuando el flag QUALITY_GATE_ENABLED=1 está
                    # activo, el dictamen pasa por pre-val → IA → post-val →
                    # regenerar si falla, en vez del call directo al IA. Cuando
                    # el flag está OFF (default) el comportamiento es idéntico
                    # al de hoy (bit-for-bit) — el path legacy sigue corriendo.
                    # El glosa_id no existe aún (la glosa se persiste DESPUÉS),
                    # por eso el sticky-canary cae al modo random.
                    _qg_resultado = None
                    try:
                        from app.services.quality_gate_adapter import (
                            debe_usar_quality_gate,
                            ejecutar_con_quality_gate,
                            registrar_estadistica_qg,
                        )

                        if debe_usar_quality_gate(glosa_id=None):
                            _proveedores = {
                                p
                                for p, k in [
                                    ("anthropic", self.anthropic_key),
                                    ("groq", self.groq),
                                ]
                                if k
                            }
                            _qg_resultado = await ejecutar_con_quality_gate(
                                servicio=self,
                                eps=str(data.eps),
                                codigo_glosa=codigo_det,
                                valor_objetado=valor_raw,
                                texto_glosa=texto_base,
                                es_ratificacion=es_ratificacion,
                                es_extemporanea=es_extemporanea,
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                glosa_id=None,
                                proveedores_disponibles=_proveedores,
                            )
                            registrar_estadistica_qg(_qg_resultado)
                    except Exception as _qg_err:
                        # Si el QG explota por cualquier razón, caemos al
                        # path legacy. NO debe afectar producción.
                        logger.warning(
                            f"[QG] adapter falló, fallback a _llamar_ia legacy: {_qg_err}"
                        )
                        _qg_resultado = None

                    if _qg_resultado and _qg_resultado.estado == "RECHAZADO_PRE":
                        # Inputs incompletos detectados ANTES de gastar IA.
                        # Devolver mensaje al usuario, no generar dictamen
                        # placebo sobre datos vacíos.
                        raise HTTPException(
                            status_code=400,
                            detail=_qg_resultado.mensaje_usuario
                            or "Inputs incompletos para generar el dictamen.",
                        )

                    if _qg_resultado and _qg_resultado.dictamen_final:
                        # QG produjo dictamen (APROBADO o ESCALAR_HUMANO con
                        # mejor intento). Sintetizamos envelope XML mínimo
                        # para que la extracción downstream funcione igual.
                        _arg_qg = _qg_resultado.dictamen_final
                        res_ia = f"<argumento>{_arg_qg}</argumento>"
                        modelo_usado = _qg_resultado.modelo_final or "qg"
                        # Marcar para que UI/postprocesador sepa que vino del
                        # QG (útil para badge "REVISAR" si ESCALAR_HUMANO).
                        self._qg_estado_actual = _qg_resultado.estado
                        self._qg_score_actual = _qg_resultado.score_final
                        _dictamen_via_qg = True
                    else:
                        # Legacy path — comportamiento de hoy
                        res_ia, modelo_usado = await self._llamar_ia(
                            system_prompt,
                            user_prompt,
                            eps=str(data.eps),
                            codigo=codigo_det,
                            modelo_override=_modelo_override,
                        )

            # ═══════════════════════════════════════════════════════════
            #  R-CEREBRO #1: Validación post-generación con retry
            #  Detecta defectos críticos (frases prohibidas, tags
            #  faltantes, citas legales mal escritas, código no
            #  mencionado, valor no textual). Si los hay, regenera UNA
            #  vez bypaseando el caché con instrucciones específicas
            #  de qué corregir.
            #  Se SALTA cuando el dictamen vino del Quality Gate: el QG
            #  ya post-validó/regeneró (hasta 3 intentos) y duplicar la
            #  validación legacy costaba hasta 2 llamadas LLM extra con
            #  veredictos potencialmente contradictorios.
            # ═══════════════════════════════════════════════════════════
            if not _dictamen_via_qg:
                try:
                    from app.services.detector_copia import (
                        detectar_copia_gold,
                    )
                    from app.services.validador_dictamen import (
                        detectar_defectos_criticos,
                        construir_instruccion_retry,
                        resumen_defectos,
                    )

                    _defectos = detectar_defectos_criticos(
                        res_ia,
                        codigo_glosa=codigo_det,
                        valor_objetado=valor_raw,
                        tiene_contrato=tiene_contrato,
                        valor_facturado=_val_fact_str,
                        es_ratificacion=es_ratificacion,
                        es_extemporanea=es_extemporanea,
                        codigo_respuesta=cod_res,
                    )
                    # Mejora #7: chequear si el dictamen es copia textual
                    # de algún ejemplo Gold inyectado. Si lo es, eso es un
                    # defecto crítico equivalente y forzamos retry.
                    _copia = None
                    if _ejemplos_gold:
                        try:
                            # Extraer solo el contenido de <argumento>
                            import re as _re_arg

                            _m_arg = _re_arg.search(
                                r"<argumento>(.*?)</argumento>",
                                res_ia or "",
                                _re_arg.DOTALL | _re_arg.IGNORECASE,
                            )
                            _arg_solo = _m_arg.group(1) if _m_arg else (res_ia or "")
                            _copia = detectar_copia_gold(
                                _arg_solo,
                                _ejemplos_gold,
                                umbral=0.55,
                            )
                            if _copia:
                                _defectos.append(
                                    {
                                        "regla": "copia_textual_gold",
                                        "mensaje": (
                                            f"El dictamen es {_copia['similitud'] * 100:.0f}% "
                                            "idéntico a un ejemplo Gold."
                                        ),
                                        "sugerencia": (
                                            "Reformula con vocabulario propio. "
                                            "Mantén estructura y normas pero "
                                            "cambia las palabras."
                                        ),
                                    }
                                )
                                logger.warning(
                                    f"[VALIDACION-IA] Copia textual detectada: "
                                    f"{_copia['similitud'] * 100:.0f}% similitud con "
                                    f"ejemplo {_copia['fuente']} #{_copia['ejemplo_id']}"
                                )
                        except Exception as _e_c:
                            logger.debug(f"Detector copia falló: {_e_c}")
                    # Heurística de costo: si el ÚNICO defecto es
                    # "demasiado_largo", el retry rara vez mejora (el LLM
                    # vuelve a producir longitud similar) y gastamos
                    # ~$0.05 + ~25s en latencia por nada. Tratamos esa
                    # regla como soft warning y NO disparamos retry.
                    _solo_largo = (
                        len(_defectos) == 1 and _defectos[0].get("regla") == "demasiado_largo"
                    )
                    if _solo_largo:
                        logger.info(
                            "[VALIDACION-IA] Solo demasiado_largo — "
                            "retry omitido para ahorrar tokens (~$0.05). "
                            "Aceptando primera respuesta."
                        )
                    if _defectos and not _solo_largo:
                        logger.warning(
                            f"[VALIDACION-IA] Defectos detectados en primera "
                            f"respuesta: {resumen_defectos(_defectos)}"
                        )
                        instr_retry = construir_instruccion_retry(_defectos)
                        user_retry = user_prompt + instr_retry
                        try:
                            res_retry, _modelo_retry = await self._llamar_ia(
                                system_prompt,
                                user_retry,
                                eps=str(data.eps),
                                codigo=codigo_det,
                                modelo_override=_modelo_override,
                                bypass_cache=True,
                            )
                            # Aceptamos la nueva respuesta solo si tiene
                            # MENOS defectos críticos que la primera
                            _defectos_retry = detectar_defectos_criticos(
                                res_retry,
                                codigo_glosa=codigo_det,
                                valor_objetado=valor_raw,
                                tiene_contrato=tiene_contrato,
                                valor_facturado=_val_fact_str,
                                es_ratificacion=es_ratificacion,
                                es_extemporanea=es_extemporanea,
                                codigo_respuesta=cod_res,
                            )
                            if len(_defectos_retry) < len(_defectos):
                                logger.info(
                                    f"[VALIDACION-IA] Retry mejoró: "
                                    f"{len(_defectos)} → {len(_defectos_retry)} defectos"
                                )
                                res_ia = res_retry
                                modelo_usado = _modelo_retry
                            else:
                                logger.warning(
                                    "[VALIDACION-IA] Retry no mejoró — usando primera respuesta"
                                )
                        except Exception as _e:
                            logger.warning(f"Retry IA por validación falló: {_e}")
                except Exception as _e:
                    logger.debug(f"Validación post-gen no aplicada: {_e}")

            razonamiento = self._xml("razonamiento", res_ia, "")
            if razonamiento:
                logger.info(f"IA razonamiento: {razonamiento[:200]}")

            pac_ia = self._xml("paciente", res_ia, "NO IDENTIFICADO")
            servicio_ia = self._xml("servicio", res_ia, "")
            contrato_ia = self._xml("contrato", res_ia, "")
            tarifa_ia = self._xml("tarifa", res_ia, "")
            arg_ia = self._xml("argumento", res_ia, "")
            normas_clave = self._xml("normas_clave", res_ia, "")
            # Decisión autónoma de la IA (R-cerebro #8)
            accion_ia = (self._xml("accion", res_ia, "") or "").strip().upper()
            try:
                _va = self._xml("valor_aceptar", res_ia, "0") or "0"
                valor_aceptar_ia = float(re.sub(r"[^\d.]", "", _va) or 0)
            except Exception:
                valor_aceptar_ia = 0.0
            try:
                _vd = self._xml("valor_defender", res_ia, "0") or "0"
                valor_defender_ia = float(re.sub(r"[^\d.]", "", _vd) or 0)
            except Exception:
                valor_defender_ia = 0.0
            if accion_ia:
                logger.info(
                    f"[IA-ACCION] {accion_ia} aceptar=${valor_aceptar_ia:,.0f} "
                    f"defender=${valor_defender_ia:,.0f}"
                )

            if not arg_ia or arg_ia == res_ia:
                if "<argumento>" in res_ia:
                    start = res_ia.find("<argumento>") + len("<argumento>")
                    end = res_ia.find("</argumento>")
                    arg_ia = res_ia[start:end].strip() if end > start else res_ia
                else:
                    arg_ia = res_ia

            # Ronda 3 (16-jun-2026): sanitizador de chain-of-thought ANTES
            # de cualquier otro procesamiento. Razonadores como qwen3 (y
            # ocasionalmente gpt-oss) emiten razonamiento en inglés ("Let
            # me go through each section step by step...", "```xml",
            # "tags.") ANTES de las tags XML — y cuando arg_ia cae al
            # fallback res_ia entero, ese razonamiento llega al dictamen.
            arg_ia = _limpiar_chain_of_thought(arg_ia)

            if not arg_ia:
                logger.warning(
                    f"[DICTAMEN-VACIO] arg_ia vacío tras extracción XML. "
                    f"modelo={modelo_usado!r} res_ia_len={len(res_ia or '')} "
                    f"res_ia_preview={repr((res_ia or '')[:200])}"
                )

            if not normas_clave and "<normas_clave>" in res_ia:
                start = res_ia.find("<normas_clave>") + len("<normas_clave>")
                end = res_ia.find("</normas_clave>")
                normas_clave = res_ia[start:end].strip() if end > start else ""

            if "<paciente>" in arg_ia:
                arg_ia = arg_ia.split("</paciente>")[-1].strip()
            # Expandir abreviaturas de códigos a nombres completos
            arg_ia = _expandir_abreviaturas_tipo(arg_ia)
            # Safety net: limpiar placeholders y construcciones gramaticales
            # rotas que la IA suele producir cuando no tiene monto numérico.

            # 1) "$EL VALOR INDICADO…" / "$VALOR FACTURADO…" → sin $
            arg_ia = re.sub(
                r"\$\s*(EL\s+)?VALOR\s+(FACTURADO|OBJETADO|ACEPTADO|INDICADO)",
                lambda m: (m.group(1) or "EL ") + f"VALOR {m.group(2)}",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 2) "VALOR DE EL VALOR INDICADO EN EL EXPEDIENTE" (redundancia)
            arg_ia = re.sub(
                r"VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
                r"VALOR INDICADO EN EL EXPEDIENTE",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 3) "RETENCIÓN DE EL VALOR" / "RETENCIÓN DE $EL VALOR"
            arg_ia = re.sub(
                r"RETENCI[ÓO]N\s+DE\s+\$?\s*EL\s+VALOR",
                r"RETENCIÓN DEL VALOR",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 4) "FACTURADO POR VALOR DE EL VALOR INDICADO..." → "FACTURADO SEGÚN CONSTA..."
            arg_ia = re.sub(
                r"FACTURAD[OA]\s+POR\s+VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
                r"FACTURADO SEGÚN CONSTA EN EL EXPEDIENTE",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 5) "RECONOCIMIENTO ÍNTEGRO DEL VALOR DE EL VALOR INDICADO..."
            arg_ia = re.sub(
                r"RECONOCIMIENTO\s+(ÍNTEGRO\s+)?DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)",
                r"RECONOCIMIENTO \1DEL VALOR \2",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 6) Preposición "DE EL" → "DEL"
            arg_ia = re.sub(r"\bDE\s+EL\s+VALOR\b", "DEL VALOR", arg_ia, flags=re.IGNORECASE)

            # 7) Terminología Sanidad Militar: "FUERZAS ARMADAS" → "FUERZAS MILITARES"
            arg_ia = re.sub(
                r"\bFUERZAS\s+ARMADAS\b", "FUERZAS MILITARES", arg_ia, flags=re.IGNORECASE
            )
            arg_ia = re.sub(r"\bFF\.?\s*AA\b\.?", "FF.MM.", arg_ia)
            arg_ia = re.sub(r"FF\.MM\.\.", "FF.MM.", arg_ia)  # doble punto si aplicó 2 veces

            # 8) Verbos normativos en pretérito → presente (las normas vigentes rigen en presente)
            # Cubre: ARTÍCULO X, LEY X, RESOLUCIÓN X, DECRETO X, ACUERDO X, CIRCULAR X seguido de verbo en pretérito
            _PRETERITO_PRESENTE = [
                (r"\bCONSAGR[ÓO]\b", "CONSAGRA"),
                (r"\bESTABLECI[ÓO]\b", "ESTABLECE"),
                (r"\bREAFIRM[ÓO]\b", "REAFIRMA"),
                (r"\bDISPUSO\b", "DISPONE"),
                (r"\bRECONOCI[ÓO]\b(?!\s+COMO)", "RECONOCE"),
                (r"\bOBLIG[ÓO]\b", "OBLIGA"),
                (r"\bIMPUSO\b", "IMPONE"),
                (r"\bCONFIRM[ÓO]\b", "CONFIRMA"),
            ]
            for pat, repl in _PRETERITO_PRESENTE:
                arg_ia = re.sub(pat, repl, arg_ia, flags=re.IGNORECASE)

            # 9) Tipos de errores OCR / typos comunes de la IA
            arg_ia = re.sub(r"\bCONSAGR\s+A\b", "CONSAGRA", arg_ia, flags=re.IGNORECASE)
            arg_ia = re.sub(r"\bGLosa\b", "GLOSA", arg_ia)
            arg_ia = re.sub(r"\bGLosas\b", "GLOSAS", arg_ia)
            arg_ia = re.sub(r"\bGLosA\b", "GLOSA", arg_ia)

            # 9b) Limpieza de sintaxis Markdown que la IA inserta sola.
            # Caso típico: [CARTERA@HUS.GOV.CO](mailto:CARTERA@HUS.GOV.CO)
            # se queda como texto crudo en el panel HTML porque el motor
            # no procesa Markdown. Lo bajamos al email plano.
            arg_ia = re.sub(
                r"\[([^\]]+)\]\(mailto:([^)]+)\)",
                lambda m: m.group(1) if "@" in m.group(1) else m.group(2),
                arg_ia,
            )
            # Enlaces Markdown genéricos [texto](url) → texto (sin URL)
            arg_ia = re.sub(
                r"\[([^\]]+)\]\(https?://[^)]+\)",
                r"\1",
                arg_ia,
            )
            # **negrita** y __negrita__ Markdown → texto plano
            arg_ia = re.sub(r"\*\*([^\*]+)\*\*", r"\1", arg_ia)
            arg_ia = re.sub(r"__([^_]+)__", r"\1", arg_ia)
            # Headers Markdown al inicio de línea (### Título → Título)
            arg_ia = re.sub(r"(?m)^#{1,6}\s+", "", arg_ia)

            # 10) Typos inventados por la IA (palabras que no existen)
            _TYPOS_IA = {
                r"\bSERJURAR\b": "ESTAR SUJETA A",
                r"\bSERJUROS\b": "SUJETOS",
                r"\bREINTEGRAMENTE\b": "ÍNTEGRAMENTE",
                r"\bDISPUSIO\b": "DISPONE",
                r"\bCONFIGURANDO\s+UN\s+INCUMPLIMIENTO\b": "CONFIGURA UN INCUMPLIMIENTO",
            }
            for pat, repl in _TYPOS_IA.items():
                arg_ia = re.sub(pat, repl, arg_ia, flags=re.IGNORECASE)

            # 10b) Sanitizer global: eliminar "injustificado/a/os/as" en
            # todas sus formas (directiva ESE HUS mayo 2026 — Yesid).
            # Reemplaza por sinónimos profesionales sin la raíz "injustific".
            # EXCEPCION: si el codigo de respuesta resuelto es RE9602
            # ('Glosa Injustificada al 100%'), la palabra SI debe aparecer
            # porque es el concepto canonico del catalogo oficial.
            arg_ia = limpiar_palabra_injustificado(arg_ia, codigo_respuesta=cod_res)

            # 10c) Sanitizer cierre canónico: el bloque "...10 DÍAS HÁBILES...
            # MESA DE CONCILIACIÓN... COMUNICACIONES: CARTERA@HUS.GOV.CO,
            # GLOSASYDEVOLUCIONES@HUS.GOV.CO" SOLO debe aparecer en respuestas
            # de tipo RATIFICADA o EXTEMPORÁNEA. Para defensas normales,
            # aceptaciones (totales/parciales) y demás casos, este cierre
            # es ruidoso e innecesario — Yesid pidió eliminarlo.
            arg_ia = limpiar_cierre_extemporanea_indebido(
                arg_ia,
                es_ratificacion=es_ratificacion,
                es_extemporanea=es_extemporanea,
                codigo_respuesta=cod_res,
            )

            # 11) Limpieza minima de PHI: solo conectores o formatos rotos,
            # PERO conservamos nombres y numero de HC porque son base argumental
            # para la defensa ante la entidad pagadora.
            # Nota: si quieres anonimizar para alguna glosa especifica, hazlo
            # manualmente con "Refinar con IA" pidiendo el cambio.

            # 12) Dobles conectores redundantes
            arg_ia = re.sub(
                r"\b(ADICIONALMENTE|ASIMISMO|IGUALMENTE),\s*(POR\s+SU\s+PARTE|EN\s+IDÉNTICO\s+SENTIDO)",
                r"\1",
                arg_ia,
                flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"\b(POR\s+SU\s+PARTE),\s*(ADICIONALMENTE|ASIMISMO|IGUALMENTE|EN\s+IDÉNTICO\s+SENTIDO)",
                r"\1",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 13) Anti-runaway: detectar y truncar bucles de repetición
            # (cuando la IA entra en degenerate state y repite "DEL X DEL X DEL X...")
            arg_ia = _truncar_runaway(arg_ia)

            # 13b) Dedup de oraciones largas repetidas — la misma cláusula
            # citada 2 veces en el mismo dictamen (caso real 10-jun-2026)
            arg_ia = _dedup_oraciones_largas(arg_ia)

            # 14) Corregir "DISPOSICIONADO" inventado por IA → DISPENSARIO
            arg_ia = re.sub(
                r"\bDISPOSICIONADO\b", "DISPENSARIO MÉDICO", arg_ia, flags=re.IGNORECASE
            )

            # 15) ESTÁNDAR INSTITUCIONAL: respuestas a glosas SIEMPRE en MAYÚSCULAS
            # Si la IA mezcló casing o devolvió en minúsculas, forzamos upper.
            letras = [c for c in arg_ia if c.isalpha()]
            if letras:
                ratio_mayus = sum(1 for c in letras if c.isupper()) / len(letras)
                # Si <80% está en mayúsculas, forzar todo a mayúsculas
                if ratio_mayus < 0.80:
                    arg_ia = arg_ia.upper()
                    # Re-aplicar expansión de abreviaturas por si falló
                    arg_ia = _expandir_abreviaturas_tipo(arg_ia)

            # 16) ANTI-ALUCINACIÓN DE MONTOS + PLACEHOLDERS (CRÍTICO):
            # 16a) Placeholders literales tipo "$[VALOR_OBJETADO]",
            # "$[DIFERENCIA]", "$[TOTAL_FACTURADO]" que la IA a veces deja
            # sin renderizar. Siempre se reemplazan, incluso si hay valor.
            arg_ia = re.sub(
                r"\$\s*\[[A-Z_ ]+\]",
                "EL VALOR INDICADO EN EL EXPEDIENTE",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 16a-bis) Placeholders crudos SIN prefijo $ (12-jun-2026,
            # ronda 2 — fix #6): "[ENTIDAD]", "[SERVICIO]", "[VALOR REAL]",
            # "[CODIGO]" salieron literales en un dictamen ENTREGADO. Se
            # rellenan con los datos reales del caso; si queda alguno sin
            # equivalencia, _rellenar_placeholders deja warning y el score
            # lo descuenta más abajo.
            arg_ia = _rellenar_placeholders(
                arg_ia,
                eps=str(data.eps or ""),
                codigo=codigo_det,
                valor=valor_raw,
            )

            # 16b) Si el texto original de la glosa NO traía un valor numérico,
            # la IA NO debe inventar cifras. Reemplazamos montos específicos.
            _no_hay_valor_original = (not valor_raw) or valor_raw.strip() in (
                "$ 0.00",
                "$0.00",
                "$ 0",
            )
            if _no_hay_valor_original:
                # Patrón: $ seguido de cifras con separadores (. , ) opcionales
                _patron_monto = re.compile(
                    r"\$\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?",
                    flags=re.IGNORECASE,
                )
                arg_ia = _patron_monto.sub("EL VALOR INDICADO EN EL EXPEDIENTE", arg_ia)

            # 16c) Limpieza de frases rotas post-reemplazo (con o sin valor)
            arg_ia = re.sub(
                r"FACTURADO\s+POR\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "FACTURADO SEGÚN VALOR INDICADO EN EL EXPEDIENTE",
                arg_ia,
                flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"Y\s+RECONOCIDO\s+SOLO\s+POR\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "Y RECONOCIDO PARCIALMENTE POR LA ENTIDAD PAGADORA",
                arg_ia,
                flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"RETENCI[ÓO]N\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "LA DIFERENCIA INDICADA EN EL EXPEDIENTE",
                arg_ia,
                flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"RECONOCIMIENTO\s+ÍNTEGRO\s+DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO",
                arg_ia,
                flags=re.IGNORECASE,
            )

            # 17) TONO INSTITUCIONAL CONCILIADOR + FRASES ROTAS (safety net
            # compartido con el camino de texto fijo). Ver _suavizar_tono.
            # R59 P3: SALTAR _suavizar_tono en modo auditoria_previa — el
            # output ya es HTML estructurado neutral con secciones fijas;
            # cualquier sustitución de frases (ej. "SE EXIGE EL LEVANTAMIENTO"
            # → "SE SOLICITA…") rompería el formato del informe de auditoría.
            if modo_resp != "auditoria_previa":
                arg_ia = _suavizar_tono(arg_ia)

            # Guard-rail: recortar coda procesal después del cierre canónico
            # ("SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA..."). Se aplica AQUÍ
            # — sobre el texto plano del argumento, antes de envolverlo en
            # HTML — para no romper la estructura del dictamen ni cortar los
            # bloques posteriores (Servicio/Contrato/Tarifa/Normativa).
            from app.services.dictamen_postprocesor import (
                quitar_citas_invalidas_dinamico,
                quitar_parrafos_con_citas_inventadas,
                truncar_despues_de_levantamiento,
            )

            # 1. Quitar oraciones que mencionan citas inventadas frecuentes
            #    (lista negra estática — rápido)
            arg_ia = quitar_parrafos_con_citas_inventadas(arg_ia)
            # 2. Quitar citas inválidas DINÁMICAMENTE usando el verificador
            #    oficial contra el corpus normativo cargado. Cubre casos que
            #    no están en la lista negra estática (mayo 2026 — Yesid).
            arg_ia = quitar_citas_invalidas_dinamico(arg_ia, eps=str(data.eps or ""))
            # 3. Truncar coda procesal después del cierre canónico
            arg_ia = truncar_despues_de_levantamiento(arg_ia)

            # AUTO-CRÍTICA: valida el borrador y pide corrección si es pobre.
            # Solo aplica en modo normal (no auditoria_previa, no texto-fijo).
            # Se limita a 1 iteración para no aumentar latencia >2x.
            # Funciona con cualquier proveedor de dictámenes (Anthropic/
            # Groq) via _llamar_ia que respeta primary_ai + fallback.
            _hay_proveedor = bool(self.anthropic_key or self.groq)
            if modo_resp != "auditoria_previa" and _hay_proveedor:
                try:
                    from app.services.validador_dictamen import evaluar_dictamen

                    _texto_eval = arg_ia.replace("<br/>", " ").replace("*", "")
                    _resultado_val = evaluar_dictamen(
                        argumento_html=_texto_eval,
                        cups_esperado=None,
                        valor_original=valor_raw,
                        codigo_respuesta=cod_res,
                        codigo_glosa=codigo_det,
                    )
                    _score_val = _resultado_val.get("score", 100)
                    _defectos = [
                        d for d in _resultado_val.get("checks", []) if not d.get("aprobado", True)
                    ]

                    # Solo refinar si score < 70 y hay defectos específicos
                    if _score_val < 70 and _defectos:
                        _feedback_items = "\n".join(
                            f"- {d.get('nombre', '?')}: {d.get('mensaje', '')}"
                            for d in _defectos[:5]
                        )
                        _refine_prompt = (
                            f"El dictamen que generaste tiene un score de calidad de {_score_val}/100. "
                            f"Los problemas detectados son:\n{_feedback_items}\n\n"
                            f"Dictamen actual:\n{_texto_eval}\n\n"
                            f"Reescríbelo corrigiendo EXACTAMENTE esos problemas. "
                            f"Usa el mismo formato XML con <argumento>...</argumento>. "
                            f"No cambies el fondo legal; solo mejora la estructura y el cumplimiento."
                        )
                        _sys_refine = (
                            "Eres un revisor de calidad de dictámenes médicos del ESE HUS. "
                            "Tu única tarea es corregir los defectos señalados y devolver "
                            "el dictamen mejorado dentro de <argumento>...</argumento>."
                        )
                        try:
                            # Usa el proveedor primary_ai (Groq/Anthropic) con su
                            # cadena de fallbacks. Temperature 0.05 solo se aplica si el
                            # proveedor es Anthropic; los demás usan su default (0.2).
                            # bypass_cache=True para no servir el mismo dictamen defectuoso
                            # ya cacheado — necesitamos fuerza nueva generación.
                            _res_refinado, _modelo_refinado = await self._llamar_ia(
                                system=_sys_refine,
                                user=_refine_prompt,
                                eps=str(data.eps or ""),
                                codigo=codigo_det,
                                temperature_override=0.05,
                                bypass_cache=True,
                                # Fix #9: refinamiento = tarea corta → gpt-oss
                                # con reasoning_effort 'low'.
                                llamada_corta=True,
                            )
                            _arg_refinado = self._xml("argumento", _res_refinado, "")
                            if _arg_refinado and len(_arg_refinado) > 100:
                                arg_ia = _arg_refinado
                                # CRÍTICO: re-aplicar TODOS los sanitizers post-refinamiento.
                                # La IA refinada puede meter de nuevo coda procesal,
                                # palabra "injustificado", etc. Si no re-corremos los
                                # sanitizers, el guard-rail post-IA queda anulado.
                                if modo_resp != "auditoria_previa":
                                    arg_ia = _suavizar_tono(arg_ia)
                                arg_ia = limpiar_palabra_injustificado(
                                    arg_ia, codigo_respuesta=cod_res
                                )
                                arg_ia = limpiar_cierre_extemporanea_indebido(
                                    arg_ia,
                                    es_ratificacion=es_ratificacion,
                                    es_extemporanea=es_extemporanea,
                                    codigo_respuesta=cod_res,
                                )
                                arg_ia = quitar_parrafos_con_citas_inventadas(arg_ia)
                                arg_ia = quitar_citas_invalidas_dinamico(
                                    arg_ia, eps=str(data.eps or "")
                                )
                                arg_ia = truncar_despues_de_levantamiento(arg_ia)
                                logger.info(
                                    f"[AUTO-CRITICA] score={_score_val}→refinado "
                                    f"({len(_defectos)} defectos corregidos) "
                                    f"via {_modelo_refinado}"
                                )
                        except Exception as _e_ref:
                            logger.warning(f"[AUTO-CRITICA] refinamiento falló: {_e_ref}")
                except Exception as _e_val:
                    logger.debug(f"[AUTO-CRITICA] validación falló: {_e_val}")

            arg_limpio = arg_ia.replace("<br/>", " ").replace("*", "")
            arg_ia = arg_ia.replace("\n", "<br/>").replace("*", "")

        score = self._calcular_score(
            tipo_glosa,
            es_extemporanea,
            es_ratificacion,
            tiene_pdf,
            es_urgencia,
            es_tarifa,
            arg_limpio,
        )

        # Ronda 2 (12-jun-2026, fix #6): si tras el sanitizer quedó algún
        # [PLACEHOLDER] crudo en el argumento, el dictamen NO está listo
        # para radicar — warning + descuento en el gauge para que el gestor
        # lo vea. En los flujos con Quality Gate el post_validator además lo
        # marca GRAVE (regenera).
        try:
            _residuales_ph = _PAT_PLACEHOLDER_CRUDO.findall(arg_limpio or "")
            if _residuales_ph:
                logger.warning(
                    f"[PLACEHOLDERS] dictamen final con {len(_residuales_ph)} "
                    f"placeholder(s) crudo(s): {_residuales_ph[:3]} — score penalizado."
                )
                score = max(0, score - 10)
        except Exception:
            pass

        # R59 P3: en modo auditoría usamos wrapper minimal — el LLM ya
        # produjo el HTML estructurado con 6 secciones del informe; añadir
        # tabla de defensa + bloque normas + bloque servicio confundiría
        # al lector y rompería la estructura visual del diagnóstico.
        if modo_resp == "auditoria_previa":
            dictamen = self._wrapper_auditoria_html(
                codigo=codigo_det,
                eps=data.eps,
                contenido_html=arg_ia,
                numero_factura=data.numero_factura,
                numero_radicado=data.numero_radicado,
            )
        else:
            dictamen = self._generar_dictamen_html(
                codigo_det,
                valor_raw,
                cod_res,
                desc_res,
                arg_ia,
                data.eps,
                tipo_glosa,
                numero_factura=data.numero_factura,
                numero_radicado=data.numero_radicado,
                normas_clave=normas_clave if normas_clave else None,
                servicio=servicio_ia if servicio_ia else None,
                contrato=contrato_ia if contrato_ia else None,
                tarifa=tarifa_ia if tarifa_ia else None,
            )

        # ═══════════════════════════════════════════════════════════
        #  Multi-código: un dictamen por código (jun-2026).
        #  Glosas EPS con varios códigos en la misma fila ("SO0601 +
        #  TA0201 + TA0701") recibían respuesta solo del primero y el
        #  dictamen mezclaba familias sin declararlas. Ahora: encabezado
        #  con TODOS los códigos + sección del principal (flujo de
        #  arriba, intacto) + una sección IA por código adicional, cada
        #  una protegida por el Quality Gate. Todo en el MISMO registro
        #  (resultado.codigo_glosa sigue siendo el principal — sin
        #  cambios de BD ni de radicación).
        #  NO aplica a ratificadas/extemporáneas (defensas procesales
        #  que cubren la glosa COMPLETA — fragmentarlas por código las
        #  debilitaría) ni a aceptaciones/auditoría previa (no hay
        #  defensa por concepto que generar).
        # ═══════════════════════════════════════════════════════════
        _mc = None
        _aplica_mc = False
        try:
            from app.services import multi_codigo as _mc

            _aplica_mc = (
                len(codigos_detectados) > 1
                and _mc.multi_codigo_habilitado()
                and modo_resp == "defender"
                and not es_ratificacion
                and not es_extemporanea
            )
        except Exception as _e_mc_imp:
            logger.warning(f"[MULTI-CODIGO] módulo no disponible: {_e_mc_imp}")
        if _aplica_mc:
            _mc_adicionales = codigos_detectados[1 : _mc.MAX_CODIGOS_DICTAMEN]
            _mc_excedentes = codigos_detectados[_mc.MAX_CODIGOS_DICTAMEN :]
            try:
                _mc_secciones, _mc_fallidos = await _mc.generar_secciones_adicionales(
                    servicio=self,
                    codigos=_mc_adicionales,
                    codigo_principal=codigo_det,
                    todos_los_codigos=codigos_detectados,
                    texto_glosa=texto_base,
                    eps=str(data.eps),
                    valor_objetado=valor_raw,
                    contexto_pdf=contexto_pdf or "",
                    numero_factura=data.numero_factura,
                    numero_radicado=data.numero_radicado,
                    dias_habiles=dias,
                    es_extemporanea=es_extemporanea,
                    es_ratificacion=es_ratificacion,
                    tono=getattr(data, "tono", "conciliador") or "conciliador",
                    proveedores_disponibles={
                        p
                        for p, k in [
                            ("anthropic", self.anthropic_key),
                            ("groq", self.groq),
                        ]
                        if k
                    },
                )
                dictamen = (
                    _mc.construir_encabezado_html(codigos_detectados, no_procesados=_mc_excedentes)
                    + dictamen
                    + _mc_secciones
                    + _mc.construir_nota_fallidos_html(_mc_fallidos)
                )
                if _mc_fallidos:
                    logger.warning(
                        f"[MULTI-CODIGO] códigos sin sección automática: {_mc_fallidos} "
                        "— anotados en el dictamen para respuesta manual."
                    )
            except Exception as _e_mc:
                # El dictamen del código principal JAMÁS se pierde por un
                # fallo de los bloques adicionales: se entrega tal cual con
                # la nota de los códigos pendientes de respuesta manual.
                logger.warning(
                    f"[MULTI-CODIGO] secciones adicionales fallaron: {_e_mc} "
                    "— se entrega solo el dictamen del código principal."
                )
                try:
                    dictamen = dictamen + _mc.construir_nota_fallidos_html(list(_mc_adicionales))
                except Exception:
                    pass

        # Calcular riesgo de ratificación (heurística 0-100)
        try:
            from app.services.riesgo_ratificacion import calcular_riesgo

            riesgo = calcular_riesgo(
                codigo_glosa=codigo_det,
                eps=str(data.eps),
                tiene_contrato=tiene_contrato,
                tiene_pdf_soportes=tiene_pdf,
                texto_glosa=texto_base,
                es_extemporanea=es_extemporanea,
                es_ratificacion=es_ratificacion,
                score_dictamen=score,
            )
        except Exception as _e:
            logger.warning(f"Error calculando riesgo: {_e}")
            riesgo = None

        # Verificación de citas legales (post-IA) — detecta normas
        # inexistentes, artículos fuera de norma y citas literales falsas.
        # No bloquea el envío; sirve para que el gestor revise antes.
        verif_citas = None
        try:
            from app.services.citation_verifier import verificar_citas as _vc

            verif_citas = _vc(dictamen, eps=str(data.eps or ""))

            # ═══════════════════════════════════════════════════════════
            #  RED FINAL ronda 2 (12-jun-2026, fix #2): NUNCA radicar una
            #  cita literal FALSA. El caso osteosíntesis salió ENTREGADO
            #  con la cita inventada «...veintidós (22) días hábiles...»
            #  marcada CITA_LITERAL_FALSA ALTA porque (a) con el QG OFF el
            #  camino legacy no regenera por citas y el limpiador dinámico
            #  solo elimina citas con número de norma (no literales), y
            #  (b) con QG ON el ESCALAR_HUMANO entrega el "mejor" intento
            #  con la cita adentro. Aquí, sobre el dictamen YA ensamblado
            #  (incluye secciones multi-código), cada CITA_LITERAL_FALSA
            #  pierde las comillas → paráfrasis neutra "EN LOS TÉRMINOS
            #  DE...", y se re-verifica para que el badge refleje el texto
            #  final.
            # ═══════════════════════════════════════════════════════════
            try:
                if verif_citas and verif_citas.get("issues"):
                    _dictamen_descomillado = _descomillar_citas_falsas(
                        dictamen, verif_citas["issues"]
                    )
                    if _dictamen_descomillado != dictamen:
                        dictamen = _dictamen_descomillado
                        verif_citas = _vc(dictamen, eps=str(data.eps or ""))
            except Exception as _e_desc:
                # Un fallo del descomillado jamás invalida la verificación
                # ya calculada — se entrega el dictamen original con badge.
                logger.debug(f"[DESCOMILLAR-CITAS] red final no aplicada: {_e_desc}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 3 (16-jun-2026) — RED FINAL contratos ajenos.
            #  Evidencia caso 5 (DISPENSARIO MEDICO citando "440-DIGSA/
            #  DMBUG-2025"). El check_contrato_de_otra_eps del QG regenera
            #  cuando dispara, pero el legacy (QG OFF) lo deja pasar. Esta
            #  red, determinista, sustituye el número ajeno por "el
            #  contrato vigente entre las partes" antes de entregar.
            # ═══════════════════════════════════════════════════════════
            try:
                _dictamen_sin_ajeno = _neutralizar_contratos_ajenos(dictamen, str(data.eps or ""))
                if _dictamen_sin_ajeno != dictamen:
                    dictamen = _dictamen_sin_ajeno
            except Exception as _e_ca:
                logger.debug(f"[CONTRATO-AJENO] red final no aplicada: {_e_ca}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 3 (16-jun-2026) — RED FINAL CUPS falsos.
            #  Evidencia caso 4 (COOSALUD): "Verificar radicado 20260511"
            #  → la IA escribió "código CUPS 20260511" (es yyyymmdd, no
            #  CUPS). Se sustituye por "el procedimiento facturado".
            # ═══════════════════════════════════════════════════════════
            try:
                _dictamen_sin_cups_falso = _neutralizar_cups_falsos(dictamen)
                if _dictamen_sin_cups_falso != dictamen:
                    dictamen = _dictamen_sin_cups_falso
            except Exception as _e_cf:
                logger.debug(f"[CUPS-FALSO] red final no aplicada: {_e_cf}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 5 (16-jun-2026) — RED FINAL EPS inventada.
            #  Evidencia caso 4: con EPS=COOSALUD el dictamen escribió
            #  "EPS SaludCo" (nombre fabricado). Esta red sustituye
            #  cualquier "EPS X" donde X ≠ la EPS del input por "la
            #  entidad pagadora". NO toca el sintagma cuando la EPS del
            #  input es "OTRA / SIN DEFINIR" (no hay referencia).
            # ═══════════════════════════════════════════════════════════
            try:
                _dictamen_sin_eps_falsa = _neutralizar_eps_inventada(dictamen, str(data.eps or ""))
                if _dictamen_sin_eps_falsa != dictamen:
                    dictamen = _dictamen_sin_eps_falsa
            except Exception as _e_ei:
                logger.debug(f"[EPS-INVENTADA] red final no aplicada: {_e_ei}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 6 (16-jun-2026) — RED FINAL frases absurdas (fix J).
            #  Caso 10 PPL: "cualquier intento de rebatir será improcedente".
            #  Caso 12 Compensar: "Esta respuesta es definitiva y no admite
            #  rebatimiento alguno". Sin valor legal — la EPS siempre puede
            #  ratificar. Eliminadas antes de entregar.
            # ═══════════════════════════════════════════════════════════
            try:
                _dictamen_sin_absurdos = _neutralizar_frases_absurdas(dictamen)
                if _dictamen_sin_absurdos != dictamen:
                    dictamen = _dictamen_sin_absurdos
            except Exception as _e_fa:
                logger.debug(f"[FRASE-ABSURDA] red final no aplicada: {_e_fa}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 6 (16-jun-2026) — RED FINAL código coherente (fix I).
            #  Caso 9 (FOMAG): cabecera "N/A". Caso 12 (Compensar, CL0801):
            #  "CÓDIGO 12345". Caso 13 (NUEVA EPS, TA0201): "CÓDIGO 118800"
            #  (es número de factura). Si el código del dictamen no es el
            #  del input, lo corregimos.
            # ═══════════════════════════════════════════════════════════
            try:
                # En multi-código el dictamen agrupa varios códigos con
                # secciones por cada uno — todos son válidos.
                _codigos_validos = list(codigos_detectados) if codigos_detectados else None
                _dictamen_cod_ok = _normalizar_codigo_dictamen(
                    dictamen, codigo_det or "", _codigos_validos
                )
                if _dictamen_cod_ok != dictamen:
                    dictamen = _dictamen_cod_ok
            except Exception as _e_ci:
                logger.debug(f"[CODIGO-INCOHERENTE] red final no aplicada: {_e_ci}")

            # ═══════════════════════════════════════════════════════════
            #  Ronda 7 (16-jun-2026) — RED FINAL truncamiento (fix S).
            #  Caso 13 NUEVA EPS: dictamen terminó "(ART. 2284/2023».)"
            #  — paréntesis sin cerrar tras quedarse sin tokens. Cortamos
            #  al último punto limpio y agregamos petición estándar.
            # ═══════════════════════════════════════════════════════════
            try:
                _dictamen_cerrado = _cerrar_truncamiento(dictamen)
                if _dictamen_cerrado != dictamen:
                    dictamen = _dictamen_cerrado
            except Exception as _e_tr:
                logger.debug(f"[TRUNCAMIENTO] red final no aplicada: {_e_tr}")

        except Exception as _e:
            logger.debug(f"[CONFIDENCE] citation_verifier falló: {_e}")
            verif_citas = None

        # Score de confianza 0-1 + breakdown — la UI muestra badge color
        # verde/amarillo/rojo + qué le falta al dictamen.
        confianza = None
        try:
            from app.services.confidence_scorer import calcular_confianza

            # Cuenta soportes contando el separador que usa
            # app/api/routers/analizar.py:212-216 ("═══ DOCUMENTO: ... ═══").
            # Antes contaba "\n--- ARCHIVO " que no existe → soportes_n=0 siempre.
            soportes_n = 0
            try:
                txt = contexto_pdf or ""
                # Si tiene el separador ═══ DOCUMENTO: → un PDF por aparición
                soportes_n = max(soportes_n, txt.count("═══ DOCUMENTO:"))
                # Fallback al formato viejo "--- ARCHIVO " por si algún call site
                # aún lo usa (no se ha encontrado, pero defensivo).
                soportes_n = max(soportes_n, len(txt.split("\n--- ARCHIVO ")) - 1)
                soportes_n = max(0, soportes_n)
            except Exception:
                pass
            _vf = locals().get("_val_fact_str") or None
            _vp = locals().get("_val_pact_str") or None

            # Auditor pre-IA: re-ejecutamos (es deterministic + barato,
            # solo regex matching) para saber si encontró discrepancias
            # entre lo que afirma la EPS y la realidad de BD. Esto
            # alimenta el factor "auditor_sin_discrepancias" del scorer.
            _auditor_ok = False
            try:
                from app.services.auditor_glosa import auditar as _auditar

                def _num(s):
                    if not s:
                        return 0.0
                    try:
                        return float("".join(c for c in str(s) if c.isdigit() or c == "."))
                    except (ValueError, TypeError):
                        return 0.0

                _audit_res = _auditar(
                    texto_glosa=texto_base,
                    eps=str(data.eps or ""),
                    codigo=codigo_det,
                    tiene_contrato=tiene_contrato,
                    valor_facturado=_num(_vf),
                    valor_pactado=_num(_vp),
                    valor_objetado=_num(valor_raw),
                    contexto_pdf=contexto_pdf or "",
                )
                hallazgos_altos = [
                    h for h in (_audit_res.get("hallazgos") or []) if h.get("severidad") == "ALTA"
                ]
                # Sin discrepancias = auditor no encontró nada ALTA
                _auditor_ok = len(hallazgos_altos) == 0
            except Exception as _e_aud:
                logger.debug(f"[CONFIDENCE] auditor_glosa falló: {_e_aud}")
                _auditor_ok = False

            confianza = calcular_confianza(
                eps=str(data.eps or ""),
                codigo=str(codigo_det or ""),
                dictamen=dictamen,
                soportes_count=soportes_n,
                auditor_sin_discrepancias=_auditor_ok,
                valor_objetado=valor_raw,
                valor_facturado=_vf,
                valor_pactado=_vp,
                verificacion_citas=verif_citas,
            )
        except Exception as _e:
            logger.debug(f"[CONFIDENCE] confidence_scorer falló: {_e}")
            confianza = None

        # Auto-pilot v2 (Yesid mayo 2026): decide si el dictamen es
        # auto-enviable sin revisión humana basándose en confianza +
        # detección de "caso difícil" (>=5M COP + multi-conceptos).
        # El resultado se adjunta al GlosaResult para que la UI pueda
        # mostrar el badge "AUTO-PILOT: enviable / requiere revisión / intervenir".
        auto_pilot = None
        try:
            from app.services.auto_pilot_decision import decidir_auto_envio

            score_conf = (confianza or {}).get("score") if confianza else None
            auto_pilot = decidir_auto_envio(
                confianza_score=score_conf,
                valor_objetado_raw=valor_raw,
                texto_glosa=texto_base,
                soportes_count=soportes_n,
                es_ratificacion=es_ratificacion,
                es_extemporanea=es_extemporanea,
            )
        except Exception as _e_ap:
            logger.debug(f"[AUTO-PILOT] decidir_auto_envio falló: {_e_ap}")
            auto_pilot = None

        # Auditoría 10-jun-2026 P1-4: el gauge "% éxito" se calculaba ANTES
        # de verificar citas y confianza, con bonus por cada cita detectada
        # (¡las fabricadas SUBÍAN el score!) y sin descuento alguno — marcó
        # 87-92% en 10 casos de estrés mientras la confianza honesta decía
        # 41-65% REVISAR. El gestor veía dos señales contradictorias y la
        # inflada era la más visible. Ahora el gauge responde a la evidencia:
        # cada cita inválida descuenta, y nunca supera confianza_real + 10.
        score = _ajustar_score_por_evidencia(score, verif_citas, confianza)

        resultado = GlosaResult(
            tipo=f"RESPUESTA {cod_res}",
            resumen=f"DEFENSA TÉCNICA: {pac_ia}",
            dictamen=dictamen,
            codigo_glosa=codigo_det,
            valor_objetado=valor_raw,
            paciente=pac_ia,
            mensaje_tiempo=msg_tiempo,
            color_tiempo=color_tiempo,
            score=score,
            dias_restantes=max(0, DIAS_HABILES_LIMITE_EXTEMPORANEA - dias),
            modelo_ia=modelo_usado,
            riesgo_ratificacion=riesgo,
            accion_ia=(accion_ia or None),
            valor_aceptar_ia=(valor_aceptar_ia if valor_aceptar_ia > 0 else None),
            valor_defender_ia=(valor_defender_ia if valor_defender_ia > 0 else None),
            verificacion_citas=verif_citas,
            confianza=confianza,
            auto_pilot=auto_pilot,
        )
        # Memoria (Render Free 512 MB): el análisis dejó en memoria PDFs
        # decodificados, prompts grandes, y caché de respuestas IA. Si no
        # forzamos GC ahora, varios análisis seguidos llegan al límite y
        # disparan OOM kill (~90s downtime). Llamada explícita reduce
        # picos de heap entre 50-80 MB en pruebas locales.
        try:
            import gc as _gc

            _gc.collect()
        except Exception:
            pass

        # PostHog event tracking. Best-effort, no falla si está down.
        # OJO: solo enviamos métricas, NUNCA texto del paciente / dictamen.
        try:
            from app.services.posthog_service import capture

            capture(
                event="glosa_analizada",
                distinct_id=hint_gestor or "anonimo",
                properties={
                    "eps": (data.eps or "").upper()[:80],
                    "codigo_glosa": codigo_det,
                    "codigo_respuesta": cod_res,
                    "tipo_glosa": tipo_glosa,
                    "modelo_ia": modelo_usado,
                    "score": score,
                    "es_extemporanea": bool(es_extemporanea),
                    "es_ratificacion": bool(es_ratificacion),
                    "tiene_pdf": bool(tiene_pdf),
                    "valor_objetado_bucket": (
                        "<100K"
                        if valor_raw < 100_000
                        else "<1M"
                        if valor_raw < 1_000_000
                        else "<10M"
                        if valor_raw < 10_000_000
                        else ">=10M"
                    ),
                    "primary_ai_config": self.primary_ai,
                    "modo_resp": modo_resp,
                },
            )
        except Exception:
            pass  # tracking no debe romper el flujo

        return resultado

    def _calcular_score(
        self,
        tipo_glosa: str,
        es_extemporanea: bool,
        es_ratificacion: bool,
        tiene_pdf: bool,
        es_urgencia: bool,
        es_tarifa: bool,
        argumento_generado: str = "",
    ) -> float:
        if es_extemporanea:
            base = 99.0
        elif es_ratificacion:
            base = 92.0
        elif es_urgencia:
            base = 90.0
        elif es_tarifa:
            base = 75.0
        else:
            base = 85.0

        if tiene_pdf:
            base = min(100.0, base + 5.0)

        if argumento_generado:
            normas_citadas = len(
                re.findall(
                    r"(LEY\s*\d+|DECRETO\s*\d+|RESOLUCIÓN|RESOLUCIÓN\s*\d+|ART\.\s*\d+|ARTÍCULO\s*\d+|SENTENCIA)",
                    argumento_generado.upper(),
                )
            )
            bonus_normas = min(5.0, normas_citadas * 0.5)

            bonus_longitud = min(3.0, len(argumento_generado) / 300)

            base = min(100.0, base + bonus_normas + bonus_longitud)

            if normas_citadas >= 3:
                logger.info(
                    f"Score bonus: {normas_citadas} normas citadas, {len(argumento_generado)} chars"
                )

        return round(base, 1)

    def _xml(self, tag: str, texto: str, default: str) -> str:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    def _determinar_tipo_glosa(self, prefijo: str, texto: str) -> str:
        texto_lower = texto.lower()
        # 1) Extemporaneidad tiene prioridad absoluta
        if "extempor" in texto_lower or prefijo == "EX":
            return "EXT_EXTEMPORANEA"
        # 2) Si el prefijo del código es explícito, usarlo
        if prefijo == "TA":
            return "TA_TARIFA"
        elif prefijo == "SO":
            return "SO_SOPORTES"
        elif prefijo == "AU":
            return "AU_AUTORIZACION"
        elif prefijo == "CO":
            return "CO_COBERTURA"
        elif prefijo == "CL":
            return "CL_PERTINENCIA"
        elif prefijo == "PE":
            return "CL_PERTINENCIA"  # retrocompatibilidad: PE → CL
        elif prefijo == "FA":
            return "FA_FACTURACION"
        elif prefijo == "IN":
            return "IN_INSUMOS"
        elif prefijo == "ME":
            return "ME_MEDICAMENTOS"
        # 3) Sin código reconocido → detectar por keywords del texto.
        #    Orden importa: SOPORTES antes que FACTURACIÓN porque "falta de
        #    soporte" contiene "factura" implícito en muchos casos.
        #    Auditoría 10-jun-2026 P1-5: el matching por substring exacto
        #    perdía variantes reales ("injustificados" ≠ "no justificado
        #    clínicamente", "no existe evidencia" ≠ "falta de evidencia",
        #    "tornillos y placas" ≠ "dispositivo médico") → 6 de 10 glosas
        #    de texto libre caían al fallback FA y recibían plantilla
        #    genérica de contrato. Se amplían stems por familia.

        # ME tiene prioridad cuando el objeto ES un medicamento con tema
        # de cobertura ("medicamento fuera del PBS"): el módulo ME trae la
        # defensa correcta (prescripción del tratante, no-PBS→ADRES, y la
        # variante FF.MM.). Si se dejara a CO, respondía cobertura genérica.
        if (
            "medicament" in texto_lower or "farmaco" in texto_lower or "fármaco" in texto_lower
        ) and (
            "pbs" in texto_lower or "mipres" in texto_lower or "plan de beneficios" in texto_lower
        ):
            return "ME_MEDICAMENTOS"

        if any(
            p in texto_lower
            for p in [
                "soporte",
                "historia clínica",
                "historia clinica",
                "rips",
                "documento",
                "anexo",
                "epicrisis",
                "firma médica",
                "firma medica",
                "ordenes médicas",
                "ordenes medicas",
                "sin adjuntar",
                "falta de evidencia",
                # "No existe evidencia de realización del procedimiento."
                # (texto libre real 10-jun-2026) — la defensa es probatoria
                # (HC/RIPS = prueba de la prestación) → SO, no FA genérico.
                "no existe evidencia",
                "sin evidencia",
                "evidencia de realiza",
                "no se evidencia la atencion",
                "no se evidencia la atención",
            ]
        ):
            return "SO_SOPORTES"
        if any(
            p in texto_lower
            for p in [
                "tarifa",
                "liquidación",
                "liquidacion",
                "manual tarifario",
                "soat -",
                "soat menos",
                "homologación",
                "homologacion",
                "diferencia en valor",
                "descuento unilateral",
                "uvb",
            ]
        ):
            return "TA_TARIFA"
        if any(
            p in texto_lower
            for p in [
                "autorización",
                "autorizacion",
                "orden previa",
                "orden de servicio",
                "sin autorización",
                "sin autorizacion",
                "urgencia sin autorización",
                "remisión",
                "remision",
            ]
        ):
            return "AU_AUTORIZACION"
        if any(
            p in texto_lower
            for p in [
                "cobertura",
                "pbs",
                "plan de beneficios",
                "no incluido",
                "exclusión",
                "exclusion",
                "no pbs",
                "adres",
            ]
        ):
            return "CO_COBERTURA"
        if any(
            p in texto_lower
            for p in [
                "pertinencia",
                "no pertinente",
                "indicación clínica",
                "indicacion clinica",
                "criterio médico",
                "criterio medico",
                "autonomía médica",
                "autonomia medica",
                "no justificado clínicamente",
                # Estancia/UCI y calidad asistencial son disputas de
                # pertinencia clínica, no de facturación (casos reales
                # 10-jun-2026: "8 días de UCI... injustificados" y
                # "reingreso ≤15 días por manejo deficiente" caían a FA
                # y la respuesta ni mencionaba UCI/reingreso).
                "injustificad",
                " uci",
                "estancia",
                "días de hospitalizac",
                "dias de hospitalizac",
                "reingreso",
                "relación clínica",
                "relacion clinica",
                "manejo deficiente",
                "evento adverso",
                "fallecimiento",
            ]
        ):
            return "CL_PERTINENCIA"
        if any(
            p in texto_lower
            for p in [
                "insumo",
                "material",
                "precio",
                "prótesis",
                "protesis",
                "dispositivo médico",
                "dispositivo medico",
                # "Tornillos y placas no soportados contractualmente."
                # (texto libre real 10-jun-2026) — material de osteosíntesis
                # es la disputa de insumos clásica; caía a FA genérico.
                "dispositivo",
                "tornillo",
                "placa",
                "osteosíntesis",
                "osteosintesis",
                "clavo intramedular",
            ]
        ):
            return "IN_INSUMOS"
        if any(
            p in texto_lower
            for p in [
                "medicamento",
                "fármaco",
                "farmaco",
                "fórmula",
                "formula",
                "tocilizumab",
                "dosis",
                "vial",
            ]
        ):
            return "ME_MEDICAMENTOS"
        # 4) Último recurso: FACTURACIÓN como fallback
        return "FA_FACTURACION"

    def _extraer_codigo_glosa(self, texto: str) -> str:
        # Devuelve el primer código encontrado. Para detectar TODOS, usar _extraer_codigos_glosa.
        m = re.search(r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b", texto)
        return m.group(0) if m else "N/A"

    def _extraer_codigos_glosa(self, texto: str) -> list[str]:
        """Devuelve TODOS los códigos de glosa detectados (sin duplicados, en orden)."""
        encontrados = re.findall(r"\b(?:TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b", texto)
        vistos: list[str] = []
        for c in encontrados:
            if c not in vistos:
                vistos.append(c)
        return vistos

    def _extraer_valor(self, texto: str) -> str:
        """Extrae el valor monetario de la glosa. Tolera errores comunes:
          - "%150.000" o "%150000"  → typo '%' por '$' (frecuente en correos)
          - "$ 150.000" / "$150,000" / "150.000 pesos"
          - "por valor de 150.000" / "valor objetado: 150000"
          - "1'500.000" (separador apóstrofe colombiano)
          - "$850 millones" / "120 mil pesos" (multiplicadores verbales)
        Devuelve "$ <num>" formateado, o "$ 0.00" si no encuentra nada.
        """
        if not texto:
            return "$ 0.00"
        t = texto.replace("'", ".")  # 1'500.000 → 1.500.000

        # Multiplicadores verbales PRIMERO: "factura de $850 millones" se
        # extraía como "$ 850" (el regex capturaba el número y descartaba
        # la palabra) — visto en producción 10-jun-2026: la glosa entró a
        # BD con $850, el dashboard sumó +850 y el router la clasificó
        # MEDIA→Groq en vez de COMPLEJA→Claude. El número expandido se
        # devuelve en formato colombiano (puntos de miles) para que
        # cualquier parse_valor_cop downstream lo lea bien.
        m_mult = re.search(
            r"\$?\s*([\d][\d\.,]*)\s*(mil(?:es)?\s+(?:de\s+)?millones|millones|mill[oó]n|mil)\b",
            t,
            re.IGNORECASE,
        )
        if m_mult:
            from app.utils.moneda import parse_valor_cop as _pvc

            valor_num = _pvc(f"{m_mult.group(1)} {m_mult.group(2)}")
            if valor_num > 0:
                return f"$ {int(round(valor_num)):,}".replace(",", ".")

        patrones = [
            r"\$\s*([\d][\d\.,]{2,})",
            r"%\s*([\d][\d\.,]{2,})",
            r"\bvalor\s+de\s*\$?\s*([\d][\d\.,]{2,})",
            r"\bvalor\s+objetado[:\s]*\$?\s*([\d][\d\.,]{2,})",
            r"\bpor\s+valor\s+de\s*\$?\s*([\d][\d\.,]{2,})",
            r"\b([\d][\d\.,]{4,})\s*(?:pesos|cop|cop\.|col\$)\b",
        ]
        for p in patrones:
            m = re.search(p, t, re.IGNORECASE)
            if m:
                raw = m.group(1).strip().rstrip(".,")
                if any(ch.isdigit() for ch in raw):
                    return f"$ {raw}"

        # Filas pegadas desde Excel (TSV): "TA0801⇥882298⇥DESCRIPCIÓN⇥36.402⇥MOTIVO".
        # El valor viene como columna SIN '$' y los patrones de arriba no lo
        # ven → entraba $0 a BD y la recomendación decía "facturó $0"
        # (visto en producción 11-jun-2026). Heurística segura: solo celdas
        # con formato colombiano de miles (punto cada 3 dígitos, decimal
        # coma opcional) — "36.402" sí, "882298" (CUPS) no, "TA0801" no.
        if "\t" in t:
            pat_moneda_col = re.compile(r"^\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?$")
            for linea in t.splitlines():
                for celda in linea.split("\t"):
                    celda = celda.strip()
                    if pat_moneda_col.fullmatch(celda):
                        return f"$ {celda}"

        # Números deletreados en palabras (12-jun-2026, ronda 2 — fix #7):
        # "por novecientos cincuenta y dos millones de pesos" entraba como
        # $0.00. Último intento, conservador: solo corre un patrón cardinal
        # claro que TERMINA en escala (mil / millón / millones) — nada de
        # NLP; la conversión vive en moneda.palabras_a_numero.
        m_cardinal = re.search(
            r"\b((?:(?:un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|"
            r"trece|catorce|quince|dieci\w+|veinti\w+|veinte|treinta|cuarenta|cincuenta|"
            r"sesenta|setenta|ochenta|noventa|cien|ciento|doscient\w+|trescient\w+|"
            r"cuatrocient\w+|quinient\w+|seiscient\w+|setecient\w+|ochocient\w+|"
            r"novecient\w+|mil|mill[oó]n|millones|y)\s+)+(?:mil|mill[oó]n|millones))\b",
            t,
            re.IGNORECASE,
        )
        if m_cardinal:
            from app.utils.moneda import palabras_a_numero as _pan

            valor_letras = _pan(m_cardinal.group(1))
            if valor_letras > 0:
                return f"$ {int(round(valor_letras)):,}".replace(",", ".")
        return "$ 0.00"

    def _calcular_dias_habiles(self, f1, f2) -> Optional[int]:
        """Días hábiles entre f1 y f2 (strings ISO "YYYY-MM-DD...").

        Devuelve None si las fechas no se pueden parsear. ANTES devolvía 0,
        y 0 días = "DENTRO DE TÉRMINOS": un error de formato clasificaba la
        glosa como en términos y la defensa por extemporaneidad (RE9502) se
        perdía en silencio (auditoría jun-2026, P1 #5). El caller debe
        tratar None como "no se sabe" y pedir verificación de fechas.
        """
        try:
            d1 = datetime.strptime(str(f1)[:10], "%Y-%m-%d")
            d2 = datetime.strptime(str(f2)[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            logger.error(f"_calcular_dias_habiles: fechas no parseables f1={f1!r} f2={f2!r}")
            return None
        dias, curr = 0, d1
        while curr < d2:
            curr += timedelta(days=1)
            if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in FERIADOS_CO:
                dias += 1
        return dias

    def _wrapper_auditoria_html(
        self,
        codigo: str,
        eps: str,
        contenido_html: str,
        numero_factura: Optional[str] = None,
        numero_radicado: Optional[str] = None,
    ) -> str:
        """R59 P3: wrapper minimal para diagnóstico de auditoría previa.

        A diferencia de _generar_dictamen_html (orientado a defensa con
        tabla de códigos, bloque verde de servicio, soportes obligatorios,
        etc.), este wrapper solo añade:
          - Header neutral (azul) identificando que es DIAGNÓSTICO
          - Metadatos: EPS, código, factura/radicado
          - El contenido del LLM tal cual (ya viene estructurado)
          - Disclaimer: este NO es la respuesta oficial a la EPS
        """
        meta_factura = f"<span><b>Factura:</b> {numero_factura}</span>" if numero_factura else ""
        meta_radicado = (
            f"<span><b>Radicado:</b> {numero_radicado}</span>" if numero_radicado else ""
        )
        meta_sep = " · " if numero_factura and numero_radicado else ""
        meta_html = (
            f"<div style='font-size:11px;color:#64748b;margin-top:6px;'>"
            f"{meta_factura}{meta_sep}{meta_radicado}"
            f"</div>"
            if (meta_factura or meta_radicado)
            else ""
        )
        return f"""
<div style="background:#fff;border:1px solid #cbd5e1;border-radius:8px;overflow:hidden;font-family:system-ui,-apple-system,sans-serif;">
  <div style="background:linear-gradient(135deg,#1e40af 0%,#1e3a8a 100%);color:#fff;padding:14px 20px;">
    <div style="font-size:11px;letter-spacing:1.5px;opacity:.85;text-transform:uppercase;font-weight:600;">📊 Auditoría previa · Diagnóstico neutral</div>
    <div style="font-size:16px;font-weight:700;margin-top:4px;">Análisis interno de la glosa {codigo or ""} — {eps or ""}</div>
    {meta_html}
  </div>
  <div style="padding:18px 22px;font-size:13px;line-height:1.55;color:#0f172a;">
    {contenido_html}
  </div>
  <div style="background:#fef3c7;border-top:1px solid #f59e0b;padding:10px 22px;font-size:11px;color:#78350f;">
    ⚠️ <b>Importante:</b> este documento es un INFORME INTERNO de auditoría
    para apoyar la decisión del gestor. No constituye respuesta oficial a
    la EPS. Una vez decidida la acción (defender / aceptar / pedir
    información), se debe generar el dictamen formal correspondiente.
  </div>
</div>
"""

    def _generar_dictamen_html(
        self,
        codigo: str,
        valor: str,
        cod_res: str,
        desc_res: str,
        argumento: str,
        eps: str,
        tipo: str,
        numero_factura: Optional[str] = None,
        numero_radicado: Optional[str] = None,
        normas_clave: Optional[str] = None,
        servicio: Optional[str] = None,
        contrato: Optional[str] = None,
        tarifa: Optional[str] = None,
    ) -> str:
        colores = {
            "TA_TARIFA": "#1e40af",
            "SO_SOPORTES": "#7c3aed",
            "AU_AUTORIZACION": "#059669",
            "CO_COBERTURA": "#dc2626",
            "CL_PERTINENCIA": "#d97706",
            "PE_PERTINENCIA": "#d97706",
            "FA_FACTURACION": "#0891b2",
            "IN_INSUMOS": "#e11d48",
            "ME_MEDICAMENTOS": "#4f46e5",
            "EXT_EXTEMPORANEA": "#991b1b",
            "RATIFICADA": "#7c3aed",
            "EXTEMPORANEA": "#991b1b",
        }
        color = colores.get(tipo, "#1e3a8a")

        fila_trazabilidad = ""
        if numero_factura or numero_radicado:
            fila_trazabilidad = f"""
            <tr>
                <td colspan="3" style="padding:6px 10px;font-size:10px;color:#64748b;border-top:1px dashed #e2e8f0;">
                    {"N° Factura: <b>" + numero_factura + "</b>" if numero_factura else ""}
                    {"&nbsp;&nbsp;|&nbsp;&nbsp;" if numero_factura and numero_radicado else ""}
                    {"N° Radicado: <b>" + numero_radicado + "</b>" if numero_radicado else ""}
                </td>
            </tr>"""

        bloque_servicio = ""
        if servicio or contrato or tarifa:
            servicio_html = f"<div><b>Servicio objetado:</b> {servicio}</div>" if servicio else ""
            contrato_html = f"<div><b>Contrato:</b> {contrato}</div>" if contrato else ""
            tarifa_html = f"<div><b>Tarifa pactada:</b> {tarifa}</div>" if tarifa else ""
            bloque_servicio = f"""
            <div style="background:#f0fdf4;border:2px solid #16a34a;border-radius:8px;padding:12px;margin-top:10px;">
                {servicio_html}{contrato_html}{tarifa_html}
            </div>"""

        bloque_normas = ""
        if normas_clave:
            normas_html = normas_clave.replace("|", "<br>")
            bloque_normas = f"""
            <div style="background:#dbeafe;border:2px solid #3b82f6;border-radius:8px;padding:12px;margin-top:10px;">
                <div style="font-weight:bold;color:#1e40af;margin-bottom:8px;">FUNDAMENTO NORMATIVO — 3 normas más relevantes para este caso:</div>
                <div style="color:#1e3a8a;line-height:1.8;">{normas_html}</div>
            </div>"""

        # Relación de soportes aportados (tabla) — solo si hay trazabilidad
        bloque_adjuntos = ""
        if numero_factura or numero_radicado:
            filas_adj = [
                '<tr><td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">1</td>'
                '<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">Historia clínica institucional</td>'
                '<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">Res. 1995/1999</td></tr>',
                '<tr><td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">2</td>'
                '<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">RIPS radicados</td>'
                '<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">Res. 866/2021</td></tr>',
            ]
            if numero_factura:
                filas_adj.append(
                    f'<tr><td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">3</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">Factura electrónica No. {numero_factura}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px solid #e2e8f0;">Res. 2275/2023 (FEV)</td></tr>'
                )
            bloque_adjuntos = f"""
            <div style="background:#f0fdf4;border:2px solid #16a34a;border-radius:8px;padding:12px;margin-top:10px;">
                <div style="font-weight:bold;color:#15803d;margin-bottom:8px;">📎 RELACIÓN DE SOPORTES APORTADOS</div>
                <table style="width:100%;font-size:11px;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#dcfce7;">
                            <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #16a34a;width:40px;">#</th>
                            <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #16a34a;">Documento</th>
                            <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #16a34a;width:180px;">Marco legal</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas_adj)}
                    </tbody>
                </table>
            </div>"""

        # Bloque metadatos JSON REMOVIDO — antes se incluía para parsers
        # automatizados pero aparecía como texto crudo en el PDF consolidado
        # y confundía a los lectores. Si en el futuro se necesita exponer
        # metadata a la EPS, hacerlo vía response header (p.ej. X-HUS-Meta)
        # o un endpoint JSON dedicado, no inline en el HTML del dictamen.
        bloque_metadatos = ""

        # QR de trazabilidad y carátula institucional removidos del
        # dictamen en pantalla (ruido visual). La información institucional
        # sigue presente en el PDF imprimible.
        bloque_qr = ""
        bloque_caratula = ""

        # CORRECCIÓN: nota de pie en español
        return f"""
        <table border="1" style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:15px;background:white;">
            <tr style="background-color:{color};color:white;">
                <th style="padding:10px;text-align:center;">CÓDIGO GLOSA</th>
                <th style="padding:10px;text-align:center;">VALOR OBJETADO</th>
                <th style="padding:10px;text-align:center;">CÓDIGO RESPUESTA</th>
            </tr>
            <tr>
                <td style="padding:10px;text-align:center;font-weight:bold;">{codigo}</td>
                <td style="padding:10px;text-align:center;font-weight:bold;color:{color};">{valor}</td>
                <td style="padding:10px;text-align:center;"><b>{cod_res}</b><br><span style="font-size:10px">{desc_res}</span></td>
            </tr>
            {fila_trazabilidad}
        </table>

        <div style="background:#f8fafc;border-radius:12px;padding:20px;border-left:4px solid {color};margin-top:15px;">
            <div style="display:flex;gap:10px;margin-bottom:15px;">
                <span style="background:{color};color:white;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:700;">{eps}</span>
                <span style="background:#fef3c7;color:#92400e;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:600;">{tipo.replace("_", " ")}</span>
            </div>
            <h4 style="color:#0f172a;margin:0 0 10px 0;font-size:14px;">ARGUMENTACIÓN JURÍDICA</h4>
            <div style="font-size:12px;line-height:1.9;color:#334155;white-space:pre-wrap;">{argumento}</div>
        </div>

        {bloque_servicio}
        {bloque_normas}
        {bloque_adjuntos}
        {bloque_qr}
        {bloque_caratula}
        {bloque_metadatos}

        <div style="margin-top:15px;padding:12px;background:#fef2f2;border-radius:8px;font-size:10px;color:#991b1b;">
            <b>Nota:</b> Generado con asistencia de IA. Verificar antes de radicar ante la EPS.
        </div>"""

    async def validar_pre_radicacion(
        self,
        dictamen_html: str,
        eps: str,
        codigo_glosa: str,
        valor_objetado: float,
        numero_factura: str = "",
        dias_habiles: int = 0,
    ) -> dict:
        """Valida el dictamen antes de radicarlo ante la EPS.

        Hace checks locales rápidos + un check con IA. Devuelve:
        {
            "puede_radicar": bool,
            "score_calidad": 0-100,
            "hallazgos": [{"nivel": "error|warn|info", "mensaje": "..."}],
            "resumen": "..."
        }
        """
        import re as _re
        from html import unescape

        # Extraer texto del dictamen
        txt = _re.sub(r"<[^>]+>", " ", dictamen_html or "")
        txt = _re.sub(r"\s+", " ", unescape(txt)).strip()

        hallazgos: list[dict] = []

        # 1. Checks locales (rápidos, sin IA)
        if len(txt) < 200:
            hallazgos.append(
                {"nivel": "error", "mensaje": "El argumento es muy corto (menos de 200 caracteres)"}
            )

        # Placeholders típicos olvidados
        placeholders = [
            "{EPS}",
            "{NOMBRE}",
            "{VALOR}",
            "XXXX",
            "[INSERTAR",
            "[COMPLETAR",
            "TODO:",
            "N/A NO APLICA",
        ]
        for ph in placeholders:
            if ph in txt.upper():
                hallazgos.append(
                    {
                        "nivel": "error",
                        "mensaje": f"Dictamen contiene placeholder sin rellenar: {ph}",
                    }
                )

        # EPS mencionada
        if eps and eps.upper() not in txt.upper() and "ESE HUS" in txt.upper():
            # No critico pero vale warning
            hallazgos.append(
                {"nivel": "warn", "mensaje": f"El texto no menciona explícitamente a {eps}"}
            )

        # Número de factura
        if numero_factura and numero_factura not in txt:
            hallazgos.append(
                {
                    "nivel": "warn",
                    "mensaje": f"No se encuentra el número de factura ({numero_factura}) en el texto",
                }
            )

        # Normas esperadas para el tipo
        normas_esperadas = []
        prefijo = (codigo_glosa or "")[:2].upper()
        if prefijo in ("TA",):
            normas_esperadas = ["871", "1602", "100 de 1993"]
        elif prefijo in ("SO",):
            normas_esperadas = ["1995", "1438"]
        elif prefijo in ("AU",):
            normas_esperadas = ["168", "5269"]
        elif prefijo in ("CO",):
            normas_esperadas = ["5269", "Beneficios"]
        elif prefijo in ("CL", "PE"):
            normas_esperadas = ["17", "1751"]
        elif prefijo in ("FA",):
            normas_esperadas = ["030", "Circular"]

        normas_citadas = 0
        for n in normas_esperadas:
            if n in txt:
                normas_citadas += 1
        if normas_esperadas and normas_citadas == 0:
            hallazgos.append(
                {
                    "nivel": "warn",
                    "mensaje": f"No se cita ninguna norma típica para glosas {prefijo} ({', '.join(normas_esperadas)})",
                }
            )

        # Detección de normas derogadas / incorrectas
        derogadas = {
            "1601 DEL CÓDIGO CIVIL": "Art. 1601 — posiblemente confusión con Art. 1602 (ley para las partes)",
            "RESOLUCIÓN 5926": "Res. 5926 — verificar, parece inválida (¿5269?)",
        }
        for d, msg in derogadas.items():
            if d in txt.upper():
                hallazgos.append({"nivel": "error", "mensaje": f"Cita dudosa: {msg}"})

        # Días hábiles / extemporaneidad
        if dias_habiles > 20 and "EXTEMPOR" not in txt.upper():
            hallazgos.append(
                {
                    "nivel": "warn",
                    "mensaje": f"La glosa tiene {dias_habiles} días hábiles (extemporánea) pero no se argumenta como tal",
                }
            )

        # 2. Validación normativa contra catálogo
        from app.services.normativa import validar_citas

        val_citas = validar_citas(txt)
        for d in val_citas["derogadas"]:
            msg = f"Cita derogada/confusa: {d['cita']}. {d['razon']}"
            if d.get("reemplaza_por"):
                msg += f" → usar {d['reemplaza_por']}"
            hallazgos.append({"nivel": "error", "mensaje": msg})
        if val_citas["no_catalogadas"]:
            hallazgos.append(
                {
                    "nivel": "info",
                    "mensaje": f"Citas no verificadas (pueden ser válidas): {', '.join(val_citas['no_catalogadas'][:5])}",
                }
            )

        # 3. Check con IA (si hay proveedor)
        ia_check = None
        if self.groq or self.anthropic_key:
            system_check = (
                "Eres un revisor crítico de respuestas a glosas médicas en Colombia. "
                "Revisas si el argumento es sólido antes de que la IPS lo radique ante la EPS. "
                "Marcas inconsistencias, citas jurídicas inventadas, montos que no cuadran, "
                "redacciones ambiguas o conclusiones débiles. Sé breve y directo."
            )
            user_check = (
                f"EPS: {eps}\nCódigo glosa: {codigo_glosa}\n"
                f"Valor objetado: ${valor_objetado:,.0f}\nFactura: {numero_factura}\n"
                f"Días hábiles: {dias_habiles}\n\n"
                f"ARGUMENTO A RADICAR:\n{txt[:4000]}\n\n"
                "Responde SOLO con este formato (sin preámbulos):\n"
                "PUEDE_RADICAR: SI|NO\n"
                "CALIDAD: 0-100\n"
                "RESUMEN: <una línea>\n"
                "HALLAZGOS:\n"
                "- NIVEL: ERROR|WARN|INFO — <descripción>\n"
                "(Lista vacía si no hay)"
            )
            try:
                # Fix #9: check de salida breve (PUEDE_RADICAR/CALIDAD) →
                # gpt-oss con reasoning_effort 'low'.
                res_ia, _modelo = await self._llamar_ia(
                    system_check, user_check, eps=eps, codigo=codigo_glosa, llamada_corta=True
                )
                ia_check = self._parsear_validacion_ia(res_ia)
                for h in ia_check.get("hallazgos", []):
                    hallazgos.append(h)
            except Exception as e:
                logger.warning(f"Validador IA fallo: {e}")

        # Calcular score
        errores = sum(1 for h in hallazgos if h["nivel"] == "error")
        warnings_ = sum(1 for h in hallazgos if h["nivel"] == "warn")
        score_local = max(0, 100 - (errores * 25) - (warnings_ * 8))
        score = min(score_local, ia_check.get("calidad", 100)) if ia_check else score_local

        puede_radicar = errores == 0 and score >= 60

        resumen = (
            ia_check.get("resumen")
            if ia_check and ia_check.get("resumen")
            else (
                f"{errores} error(es), {warnings_} advertencia(s)"
                if hallazgos
                else "Sin observaciones"
            )
        )

        return {
            "puede_radicar": puede_radicar,
            "score_calidad": score,
            "hallazgos": hallazgos,
            "resumen": resumen,
            "errores": errores,
            "warnings": warnings_,
            "validacion_normativa": val_citas,
        }

    @staticmethod
    def _parsear_validacion_ia(texto: str) -> dict:
        """Parsea la respuesta estructurada de la IA del validador."""
        import re as _re

        out = {"hallazgos": []}
        m = _re.search(r"PUEDE_RADICAR:\s*(SI|NO)", texto, _re.IGNORECASE)
        if m:
            out["puede_radicar"] = m.group(1).upper() == "SI"
        m = _re.search(r"CALIDAD:\s*(\d+)", texto)
        if m:
            out["calidad"] = int(m.group(1))
        m = _re.search(r"RESUMEN:\s*(.+)", texto)
        if m:
            out["resumen"] = m.group(1).strip()[:200]
        # Extraer hallazgos línea por línea
        for linea in texto.split("\n"):
            m = _re.match(r"\s*-\s*NIVEL:\s*(ERROR|WARN|INFO)\s*[-—]\s*(.+)", linea, _re.IGNORECASE)
            if m:
                out["hallazgos"].append(
                    {
                        "nivel": m.group(1).lower(),
                        "mensaje": m.group(2).strip()[:300],
                    }
                )
        return out

    async def refinar_dictamen(
        self,
        dictamen_actual_html: str,
        mensaje_usuario: str,
        eps: str = "",
        codigo: str = "",
    ) -> str:
        """Refina el dictamen existente según instrucciones del auditor.

        Retorna el nuevo argumento (texto plano con <br/> para saltos),
        listo para reemplazar la sección <div>…ARGUMENTACIÓN JURÍDICA…</div>.
        """
        # Extraer solo el argumento jurídico del HTML para no marear a la IA
        import re as _re
        from html import unescape

        txt = _re.sub(r"<[^>]+>", " ", dictamen_actual_html or "")
        txt = _re.sub(r"\s+", " ", unescape(txt)).strip()

        # Abrir por el argumento: buscar el primer marker canonico.
        # Incluye markers de inicio de argumento para CUALQUIER tipo de dictamen:
        # tarifaria/soportes (ARGUMENTACION JURIDICA), ratificada, extemporanea,
        # injustificada, etc.
        markers_inicio = (
            "ARGUMENTACIÓN JURÍDICA",
            "ARGUMENTACION JURIDICA",
            "RESPUESTA A GLOSA",
            "ESE HUS NO ACEPTA LA RATIFICACIÓN",  # ratificadas (nuevo)
            "ESE HUS NO ACEPTA",  # tarifas/facturacion/IA normal
            "ESE HUS RESPETUOSAMENTE",  # ratificadas (legacy, antes del cambio)
            "ESE HUS RECHAZA",  # Salud Total
            "ESE HUS NO COMPARTE",  # variante ratificada
        )
        for marker in markers_inicio:
            if marker in txt:
                # Si el marker aparece cerca del inicio (primeros 500 chars), cortamos por alli.
                # Si aparece mas adentro, significa que ya estamos DENTRO del argumento y lo dejamos.
                pos = txt.find(marker)
                if pos < 500:
                    # Para "ARGUMENTACIÓN JURÍDICA" y "RESPUESTA A GLOSA" son labels,
                    # cortamos DESPUES del marker.
                    if marker in (
                        "ARGUMENTACIÓN JURÍDICA",
                        "ARGUMENTACION JURIDICA",
                        "RESPUESTA A GLOSA",
                    ):
                        txt = txt[pos + len(marker) :].strip()
                    else:
                        # Para "ESE HUS..." el marker ES el inicio del argumento, cortamos DESDE el marker.
                        txt = txt[pos:].strip()
                    break

        # Cerrar por el primer marker de seccion auxiliar (soportes, QR, carátula,
        # metadatos). Lista exhaustiva para que ningún apéndice se cuele al argumento.
        cierres = (
            "📎 RELACIÓN DE SOPORTES",
            "RELACIÓN DE SOPORTES APORTADOS",
            "RELACION DE SOPORTES",
            "📲 TRAZABILIDAD",
            "TRAZABILIDAD DIGITAL",
            "CÓDIGO QR CON METADATOS",
            "CODIGO QR CON METADATOS",
            "INSTITUCIÓN PRESTADORA DE SERVICIOS",
            "INSTITUCION PRESTADORA DE SERVICIOS",
            "DOCUMENTO GENERADO ELECTRÓNICAMENTE",
            "DOCUMENTO GENERADO ELECTRONICAMENTE",
            "MARCO LEGAL: RESOLUCIÓN 2284",
            "PRESTADOR_NIT",  # JSON de metadatos embebido
            '"CODIGO_GLOSA"',
            "Nota: Generado con asistencia",
            "Nota: Generado con IA",
            "RESUMEN DE VALORES",
            "FUNDAMENTO NORMATIVO",  # por si quedó un header viejo
        )
        posiciones_cierre = [txt.find(c) for c in cierres if c in txt]
        posiciones_cierre = [p for p in posiciones_cierre if p > 0]
        if posiciones_cierre:
            primer_cierre = min(posiciones_cierre)
            txt = txt[:primer_cierre].strip()

        # Limpieza final: quitar trailing spaces, puntos repetidos, etc.
        txt = _re.sub(r"\s+\.", ".", txt)
        txt = _re.sub(r"\s+", " ", txt).strip()

        system = (
            "Eres un auditor médico senior de la ESE Hospital Universitario de Santander (HUS). "
            "Refinas argumentos técnico-jurídicos de respuesta a glosas.\n\n"
            "REGLAS CRÍTICAS (ESTRICTAS):\n"
            "1. TODA LA RESPUESTA DEBE IR EN MAYÚSCULAS. Es el estándar institucional de "
            "radicación ante EPS. No importa si el auditor pide minúsculas — MANTÉN MAYÚSCULAS. "
            "Solo respeta la instrucción del auditor en tono, longitud, citas y contenido.\n"
            "2. Las citas normativas colombianas (Ley 100/1993, Ley 1438/2011, Art. 871 "
            "C.Comercio, etc.) se conservan en su forma canónica salvo que el auditor las quite.\n"
            "3. Responde SOLO con el texto refinado del ARGUMENTO JURÍDICO — sin preámbulos, "
            "sin comillas, sin etiquetas XML, sin explicaciones de qué cambiaste, SIN incluir "
            "secciones auxiliares como 'RELACIÓN DE SOPORTES', 'TRAZABILIDAD DIGITAL', datos "
            "de la institución prestadora, fecha de emisión, ni JSON de metadatos (PRESTADOR_NIT, "
            "CODIGO_GLOSA, etc.). Esas secciones se agregan aparte por el sistema.\n"
            "4. NO inventes CUPS, folios, fechas, números de contrato ni nombres de médicos: "
            "mantén solo los datos que ya aparecen en el argumento original."
        )
        user = (
            f"EPS: {eps}\nCÓDIGO: {codigo}\n\n"
            f"ARGUMENTO ACTUAL:\n{txt}\n\n"
            f"INSTRUCCIÓN DEL AUDITOR:\n{mensaje_usuario.strip()}\n\n"
            "Devuelve SOLO el argumento refinado. No incluyas títulos como 'Respuesta:', "
            "'Argumento:', 'Relación de soportes', 'Trazabilidad', ni ningún JSON."
        )
        if not self.groq and not self.anthropic_key:
            return txt  # sin IA disponible → devolver original

        # Usa _llamar_ia para respetar PRIMARY_AI (Groq o Anthropic).
        # Fix #9: refinamiento por instrucción del auditor = tarea corta →
        # gpt-oss con reasoning_effort 'low'.
        content, _modelo = await self._llamar_ia(
            system, user, eps=eps, codigo=codigo, llamada_corta=True
        )
        out = content.strip()
        # Eliminar cierres XML si la IA los metió por hábito
        out = _re.sub(r"</?(argumento|answer|response)>", "", out, flags=_re.IGNORECASE).strip()

        # POST-LIMPIEZA: por si la IA de todas formas metió las secciones auxiliares,
        # las podamos aquí antes de devolver.
        for cierre in cierres:
            if cierre in out:
                pos = out.find(cierre)
                if pos > 100:  # no cortar si aparece muy al principio (falso positivo)
                    out = out[:pos].strip()

        # ESTÁNDAR INSTITUCIONAL: las respuestas a glosas SIEMPRE van en
        # MAYÚSCULAS (radicación ante EPS). Si la IA devolvió lowercase o
        # Title Case, forzamos upper. Preserva letras acentuadas y ñ.
        out = out.upper()
        return _expandir_abreviaturas_tipo(out)

    def _modelos_groq(self) -> list[str]:
        """Cadena de modelos Groq a intentar EN ORDEN antes de saltar a
        Anthropic (decision 12-jun-2026, ver app/core/config.py):

          1. groq_model            (default: openai/gpt-oss-120b)
          2. groq_model_fallback_1 (default: qwen/qwen3-32b)
          3. groq_model_fallback_2 (default: llama-3.3-70b-versatile)

        Dedupe preservando orden: si un override por env (p.ej.
        GROQ_MODEL=llama-3.3-70b-versatile) coincide con un fallback, ese
        modelo no se intenta dos veces.
        """
        vistos: set[str] = set()
        return [
            m
            for m in (self.groq_model, self.groq_model_fallback_1, self.groq_model_fallback_2)
            if m and not (m in vistos or vistos.add(m))
        ]

    async def _llamar_groq_con_retry(
        self, system: str, user: str, max_intentos: int = 4, llamada_corta: bool = False
    ) -> tuple[str, str]:
        """Llama a Groq con retry exponencial + cadena de modelos.

        12-jun-2026: antes de caer a Anthropic se agota la cadena de modelos
        Groq (_modelos_groq). Reglas por modelo:
          - Rate limit (429) y quedan modelos: saltar DE INMEDIATO al
            siguiente modelo (los buckets de rate limit de Groq son por
            modelo — no tiene sentido quemar backoff aqui).
          - Otro error transitorio (timeout/5xx/conexion): retry exponencial
            sobre el mismo modelo hasta `max_intentos` (presupuesto POR
            modelo), luego pasar al siguiente.
          - Error no reintentable (modelo deprecado, 400, content vacio):
            pasar al siguiente modelo sin backoff.
        Solo cuando TODOS los modelos Groq fallaron se propaga la excepcion
        (y _llamar_ia recien ahi intenta Anthropic).

        Fix #9 (12-jun-2026) — modelos razonadores openai/gpt-oss-*:
          - max_tokens sube a _GROQ_MAX_TOKENS_GPT_OSS (>=8000) porque el
            chain-of-thought se descuenta del mismo presupuesto; los demas
            modelos conservan _GROQ_MAX_TOKENS (3000).
          - reasoning_effort acota el gasto de razonamiento: 'low' si
            `llamada_corta=True` (auto-critica / refinamiento / checks),
            'medium' en dictamenes normales. Solo se envia a gpt-oss — el
            SDK documenta 'low'/'medium'/'high' para gpt-oss y otro set
            ('none'/'default') para qwen3; llama no lo soporta, y enviarlo
            a esos modelos arriesga un 400.
          - Si gpt-oss devuelve content vacio con finish_reason='length'
            (razonamiento agoto el presupuesto), se reintenta UNA vez el
            MISMO modelo con max_tokens duplicado (log [GROQ-RETRY-LENGTH])
            antes de ceder al siguiente modelo de la cadena.
        """
        ultimo_error: Exception = Exception("Groq: sin intentos")

        _ANTI_COPIA_PREFIX = (
            "ATENCION CRITICA — INSTRUCCIONES OBLIGATORIAS PARA EL MODELO:\n\n"
            "1. PROHIBIDO copia-pega del prompt. NO uses frases de los ESQUELETOS, "
            "placeholders, listas, ejemplos. Cada frase DEBE redactarse desde cero "
            "usando exclusivamente los DATOS DEL CASO concretos.\n\n"
            "2. PROHIBIDAS estas frases (las usaron antes y sonaron a plantilla):\n"
            "   - 'siendo este el sustento normativo principal'\n"
            "   - 'queda en firme la presente glosa'\n"
            "   - 'EL VALOR INDICADO EN EL EXPEDIENTE' / 'CUPS INDICADO EN EL EXPEDIENTE'\n"
            "   - 'DESCRIPCION DEL SERVICIO + CUPS' / cualquier placeholder con corchetes\n\n"
            "3. SIN DATOS = TEXTO NATURAL:\n"
            "   - Si falta valor: 'el valor objetado consignado en el expediente'\n"
            "   - Si falta CUPS: 'el procedimiento facturado conforme al CUPS de la factura'\n"
            "   - Si falta medico: 'el medico tratante registrado en historia clinica'\n\n"
            "4. NUNCA inventes: cifras, codigos CUPS, nombres, fechas, numeros de contrato.\n\n"
            "5. ESTRUCTURA OBLIGATORIA (4 parrafos NO numerados):\n"
            "   P1 IDENTIFICACION (40-60 palabras): 'ESE HUS NO ACEPTA LA GLOSA APLICADA POR "
            "CONCEPTO DE [TIPO COMPLETO] SOBRE EL CODIGO [CODIGO REAL], INTERPUESTA POR "
            "[ENTIDAD], RESPECTO DEL [SERVICIO] FACTURADO POR [VALOR REAL]...'\n"
            "   P2 REFUTACION (60-100 palabras): inicia con 'LA AFIRMACION DE LA AUDITORIA DE "
            "QUE [motivo literal EPS] NO SE AJUSTA A...' + 2-3 razones tecnicas.\n"
            "   P3 FUNDAMENTO (50-80 palabras): cita 2-3 normas reales con su numero exacto "
            "(Art. X Ley YYYY/AAAA). Si tienes CLAUSULAS DEL CONTRATO en el prompt, CITALAS "
            "TEXTUALMENTE entre comillas con su numero.\n"
            "   P4 PETICION + ESCALERA: 'EN ESE ORDEN DE IDEAS, SE SOLICITA RESPETUOSAMENTE "
            "EL LEVANTAMIENTO DE LA GLOSA [CODIGO] Y EL RECONOCIMIENTO INTEGRO. LA ENTIDAD "
            "CUENTA CON 10 DIAS HABILES (ART. 57 LEY 1438/2011). COMUNICACIONES: "
            "CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO.'\n\n"
            "6. SALIDA EN XML estricto: <paciente>, <servicio>, <contrato>, <tarifa>, "
            "<normas_clave>, <argumento>. NADA fuera de tags.\n\n"
        )
        system_reforzado = _ANTI_COPIA_PREFIX + system

        modelos = self._modelos_groq()
        for idx, modelo in enumerate(modelos):
            es_ultimo_modelo = idx == len(modelos) - 1
            # Fix #9: presupuesto y reasoning_effort por familia de modelo
            # (ver docstring). El max_tokens es mutable: el retry-por-length
            # lo duplica una vez para el mismo modelo.
            es_gpt_oss = modelo.startswith("openai/gpt-oss")
            max_tokens_modelo = _GROQ_MAX_TOKENS_GPT_OSS if es_gpt_oss else _GROQ_MAX_TOKENS
            retry_length_usado = False
            # Ronda 3 (16-jun-2026): si la API rechaza reasoning_effort
            # (parámetro renombrado/no soportado en una versión nueva del
            # endpoint), reintentar el MISMO modelo SIN ese kwarg antes de
            # ceder al siguiente. Sin esto, cada llamada a gpt-oss caía a
            # qwen — toda la ronda 3 se respondió en qwen3-32b.
            # Capability cache (ronda 5): si el proceso ya descubrió que el
            # SDK Groq rechaza `reasoning_effort`, parte con la bandera ON
            # para no repetir el TypeError en cada llamada.
            global _GROQ_SDK_SOPORTA_REASONING_EFFORT
            deshabilitar_reasoning = not _GROQ_SDK_SOPORTA_REASONING_EFFORT
            # while (no for): el retry-por-length repite el MISMO modelo con
            # max_tokens duplicado SIN consumir presupuesto de intentos.
            intento = 0
            while intento < max_intentos:
                t0 = time.monotonic()
                try:
                    kwargs_razonador: dict = {}
                    if es_gpt_oss and not deshabilitar_reasoning:
                        # gpt-oss acepta 'low'/'medium'/'high' (default
                        # medium). 'low' acota el chain-of-thought en las
                        # llamadas cortas (auto-critica/refinamiento).
                        kwargs_razonador["reasoning_effort"] = "low" if llamada_corta else "medium"
                    resp = await self.groq.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_reforzado},
                            {"role": "user", "content": user},
                        ],
                        # Modelo de la cadena Groq (12-jun-2026, ver
                        # app/core/config.py): gpt-oss-120b primario →
                        # qwen3-32b → llama-3.3-70b. El SDK de Groq acepta el
                        # id como string (endpoint compatible OpenAI), incl.
                        # prefijos "openai/" y "qwen/". Overrideable por env
                        # GROQ_MODEL / GROQ_MODEL_FALLBACK_1 / _2.
                        model=modelo,
                        temperature=0.2,
                        # 3000 tokens bastan para argumentos de 500-700
                        # palabras en modelos no razonadores; gpt-oss usa
                        # un presupuesto mayor porque el razonamiento se
                        # descuenta del mismo limite (fix #9).
                        max_tokens=max_tokens_modelo,
                        # Penalización de frecuencia/presencia evita que el modelo
                        # repita palabras/frases (anti-runaway degenerativo).
                        frequency_penalty=0.3,
                        presence_penalty=0.2,
                        timeout=120.0,
                        **kwargs_razonador,
                    )
                    choice = resp.choices[0]
                    content = choice.message.content
                    if not content:
                        finish_reason = getattr(choice, "finish_reason", None)
                        if es_gpt_oss and finish_reason == "length" and not retry_length_usado:
                            # Fix #9: el razonamiento consumió TODO el
                            # presupuesto sin emitir respuesta. UNA segunda
                            # oportunidad al mismo modelo con max_tokens
                            # duplicado antes de ceder al siguiente de la
                            # cadena (el salto a qwen queda de 2da línea).
                            retry_length_usado = True
                            nuevo_max = max_tokens_modelo * 2
                            logger.warning(
                                f"[GROQ-RETRY-LENGTH] model={modelo} "
                                f"max_tokens={max_tokens_modelo}→{nuevo_max} "
                                "(content vacío con finish_reason='length': "
                                "el razonamiento agotó el presupuesto)"
                            )
                            max_tokens_modelo = nuevo_max
                            continue
                        raise RuntimeError(
                            f"Groq/{modelo} devolvió content vacío/None "
                            f"(finish_reason={finish_reason!r})"
                        )
                    # Equivalente Groq del [ANTHROPIC-CALL]: deja claro QUE
                    # modelo respondió realmente cuando hubo fallback en la
                    # cadena (parseable desde Sentry/Loki).
                    latencia_ms = int((time.monotonic() - t0) * 1000)
                    logger.info(
                        f"[GROQ-CALL] model={modelo} latency_ms={latencia_ms} "
                        f"intento={intento + 1}/{max_intentos} "
                        f"pos_cadena={idx + 1}/{len(modelos)}"
                    )
                    return content, f"groq/{modelo}"
                except Exception as e:
                    ultimo_error = e
                    error_msg = str(e).lower()
                    tipo_error = type(e).__name__
                    # Ronda 3 (16-jun-2026): log defensivo SIEMPRE. Antes,
                    # un 400 de Groq (parámetro rechazado) caía al `break`
                    # sin loguearse — y toda la cadena se desplazaba a qwen
                    # sin que apareciera el motivo en los logs de Fly.
                    logger.warning(
                        f"[GROQ-ERROR] model={modelo} type={tipo_error} "
                        f"intento={intento + 1}/{max_intentos} "
                        f"reasoning_off={deshabilitar_reasoning} msg={str(e)[:300]}"
                    )
                    # Ronda 3: reasoning_effort rechazado (400 BadRequest
                    # con mensaje que menciona el parámetro o "unrecognized"/
                    # "extra inputs"). Reintentar el MISMO modelo SIN el
                    # parámetro antes de ceder. Hipótesis (a) confirmada en
                    # vivo si los logs muestran [GROQ-RETRY-NO-REASONING].
                    if (
                        es_gpt_oss
                        and not deshabilitar_reasoning
                        and any(
                            k in error_msg
                            for k in (
                                "reasoning_effort",
                                "reasoning effort",
                                "unknown_argument",
                                "unknown_parameter",
                                "unrecognized",
                                "extra inputs are not permitted",
                                "unsupported_parameter",
                                "unsupported parameter",
                                "invalid_request_error",
                            )
                        )
                    ):
                        deshabilitar_reasoning = True
                        # Capability cache de proceso: el SDK rechazó
                        # `reasoning_effort` UNA vez → no volver a probarlo
                        # en NINGUNA llamada futura de este proceso (los
                        # logs muestran el TypeError repetido en cada
                        # llamada cuando esto era local a la función).
                        _GROQ_SDK_SOPORTA_REASONING_EFFORT = False
                        logger.warning(
                            f"[GROQ-RETRY-NO-REASONING] model={modelo} "
                            "(API rechazó reasoning_effort — reintentando "
                            "el mismo modelo sin ese parámetro; bandera de "
                            "proceso ON para no repetirlo)"
                        )
                        continue  # mismo intento, sin sumar
                    es_rate_limit = any(k in error_msg for k in ("429", "rate_limit", "rate limit"))
                    es_reintentable = any(k in error_msg for k in _ERRORES_REINTENTABLES)
                    if es_rate_limit and not es_ultimo_modelo:
                        # Rate limit con modelos pendientes en la cadena: el
                        # siguiente modelo Groq tiene bucket de rate limit
                        # propio — saltar ya, sin quemar backoff.
                        break
                    if es_reintentable and intento < max_intentos - 1:
                        espera = min(2**intento, 16)
                        logger.warning(
                            f"[GROQ-CALL] model={modelo} error reintentable: {e}, "
                            f"reintento {intento + 2}/{max_intentos} en {espera}s"
                        )
                        await asyncio.sleep(espera)
                        intento += 1
                        continue
                    # No reintentable o presupuesto agotado → siguiente
                    # modelo de la cadena (o raise final si era el último).
                    break
            if not es_ultimo_modelo:
                logger.warning(
                    f"[GROQ-FALLBACK] model={modelo} agotado ({ultimo_error}); "
                    f"probando siguiente modelo Groq: {modelos[idx + 1]}"
                )
        raise ultimo_error

    async def _llamar_anthropic(
        self,
        system: str,
        user: str,
        modelo_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
    ) -> tuple[str, str]:
        """Llama a Claude vía API REST. Devuelve (texto, etiqueta_modelo).

        Usa **prompt caching** (optimización #3) cuando el system prompt tiene
        al menos 1024 tokens (~4000 chars). Anthropic cobra 10% del precio en
        llamadas subsecuentes con el mismo system. Para activarlo se pasa
        `system` como lista con `cache_control: {"type": "ephemeral"}`.
        Ref: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

        modelo_override: si se pasa (ej. "claude-opus-4-7" para casos de
        alta complejidad), usa ese modelo en lugar del default. Permite
        ruteo dinámico Sonnet→Opus para los casos críticos.
        temperature_override: idem para temperature.
        """
        if not self.anthropic_key:
            raise RuntimeError("Anthropic API key no configurada")
        # Ronda 49 fix: timeout más generoso para dictámenes largos con
        # max_tokens=2000. read_timeout 120s era justo y cortaba con
        # 'Stream idle timeout' en respuestas que rondaban los 100s.
        # Subimos a 180s para dar margen y activamos keepalive / retries
        # implícitos del cliente.
        _timeout_anthropic = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=10.0)

        # Decidir si usar caching: el mínimo cacheable de Anthropic es
        # 1024 tokens. Con la heurística "1 token ≈ 3 chars en español"
        # bajamos el threshold a 3000 chars (era 4000) para no perder hits
        # en system prompts cortos pero aún cacheables.
        # R53 P2: TTL extendido a 1h (default ephemeral = 5 min) → 12x más
        # cache hits durante una ráfaga de glosas. Requiere el header
        # beta 'extended-cache-ttl-2025-04-11'.
        usar_cache = bool(system and len(system) >= 3000)
        if usar_cache:
            system_payload = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ]
        else:
            system_payload = system

        # Ronda 49: retry con backoff para timeouts transitorios de red
        # (connection reset, stream idle timeout, protocolo). Hasta 3 intentos.
        _ERRORES_TRANSITORIOS = (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        )
        # Headers: si activamos cache con TTL=1h necesitamos el beta header
        # 'extended-cache-ttl-2025-04-11'. Si no, payload normal.
        _headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if usar_cache:
            _headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11"

        # R54 P3: medir latencia y costo de cada call para observabilidad.
        # Usamos time.monotonic() (no afecta a wall clock changes).
        import time as _time

        _t_inicio = _time.monotonic()

        ultimo_error = None
        for intento in range(3):
            try:
                async with httpx.AsyncClient(timeout=_timeout_anthropic) as client:
                    # Ruteo dinámico: caller puede forzar Opus 4.7 para
                    # casos de alta complejidad (mejora #5 cerebro IA).
                    _modelo_efectivo = modelo_override or self.anthropic_model
                    # Mejora #4: temperature 0.10 (era 0.15) — más
                    # consistencia en dictámenes estructurados.
                    _temp_efectiva = (
                        temperature_override if temperature_override is not None else 0.10
                    )
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=_headers,
                        json={
                            "model": _modelo_efectivo,
                            # Ronda 49: 3000 tokens es suficiente para dictamen
                            # de 800-1200 palabras; reduce latencia vs 4000.
                            "max_tokens": 3000,
                            "temperature": _temp_efectiva,
                            "system": system_payload,
                            "messages": [{"role": "user", "content": user}],
                        },
                    )
                    data = resp.json()
                    if "content" in data and data["content"]:
                        usage = data.get("usage", {})
                        latencia_ms = int((_time.monotonic() - _t_inicio) * 1000)
                        _log_metricas_anthropic(
                            usage,
                            _modelo_efectivo,
                            latencia_ms,
                        )
                        return data["content"][0]["text"], f"anthropic/{_modelo_efectivo}"
                    err = data.get("error", {}).get("message", str(data)[:300])
                    # Si es error 529 (overloaded) o 429 (rate limit), reintentar
                    status = resp.status_code
                    if status in (429, 529, 500, 502, 503, 504):
                        ultimo_error = RuntimeError(f"Anthropic HTTP {status}: {err[:200]}")
                        import asyncio as _aio

                        espera = 2.0 * (intento + 1)
                        logger.warning(
                            f"[ANTHROPIC] HTTP {status}, reintentando en {espera}s (intento {intento + 1}/3)"
                        )
                        await _aio.sleep(espera)
                        continue
                    raise RuntimeError(f"Anthropic devolvió sin 'content' (status={status}): {err}")
            except _ERRORES_TRANSITORIOS as e:
                ultimo_error = e
                import asyncio as _aio

                espera = 2.0 * (intento + 1)
                logger.warning(
                    f"[ANTHROPIC] timeout/red {type(e).__name__}, "
                    f"reintentando en {espera}s (intento {intento + 1}/3): {str(e)[:120]}"
                )
                await _aio.sleep(espera)
                continue
        # Después de 3 intentos fallidos
        raise RuntimeError(
            f"Anthropic falló tras 3 intentos por timeout/red: "
            f"{type(ultimo_error).__name__}: {str(ultimo_error)[:200]}"
        )

    async def _llamar_anthropic_con_tools(
        self,
        system: str,
        user: str,
        max_turns: int = 4,
        modelo_override: Optional[str] = None,
    ) -> tuple[str, str]:
        """Llama a Claude con TOOL USE habilitado. Multi-turn loop:
        Claude pide tools → ejecutamos → devolvemos resultado → repetimos
        hasta que Claude entrega el dictamen final o se alcanza max_turns.

        Solo se usa cuando TOOL_USE_HABILITADO=1. La idea es que Claude
        traiga del backend solo la información que realmente necesita
        (cláusulas del contrato relevantes, precedentes internos, normas)
        en vez de recibir un super-prompt con TODO inyectado a ciegas.

        Devuelve (texto_final_del_dictamen, etiqueta_modelo).
        Si todas las herramientas fallan o Claude no termina, levanta.
        """
        import httpx
        from app.services.ia_tools import TOOLS_DISPONIBLES, execute_tool

        if not self.anthropic_key:
            raise RuntimeError("Anthropic API key no configurada (tool use)")

        timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=10.0)
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Respeta el routing dinamico: si el caller pidio Haiku para
        # un caso liviano, usar Haiku tambien con Tool Use. Sino,
        # default Sonnet/configured.
        modelo_efectivo = modelo_override or self.anthropic_model
        # Historial de mensajes para el multi-turn
        messages = [{"role": "user", "content": user}]

        async with httpx.AsyncClient(timeout=timeout) as client:
            for turno in range(max_turns):
                try:
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json={
                            "model": modelo_efectivo,
                            "max_tokens": 4000,
                            "temperature": 0.10,
                            "system": system,
                            "tools": TOOLS_DISPONIBLES,
                            "messages": messages,
                        },
                    )
                except Exception as e:
                    logger.error(f"[TOOL-USE] Error de red turno {turno}: {e}")
                    raise RuntimeError(f"Tool use falló por red: {e}")

                if resp.status_code != 200:
                    logger.error(f"[TOOL-USE] HTTP {resp.status_code}: {resp.text[:300]}")
                    raise RuntimeError(f"Tool use HTTP {resp.status_code}")

                data = resp.json()
                stop_reason = data.get("stop_reason")
                contenido = data.get("content") or []

                # Agregar respuesta de Claude al historial (assistant)
                messages.append({"role": "assistant", "content": contenido})

                # ¿Claude pidió ejecutar tools?
                tool_uses = [b for b in contenido if b.get("type") == "tool_use"]
                if tool_uses and stop_reason == "tool_use":
                    # Ejecutar cada tool y devolver resultado en el siguiente mensaje
                    tool_results_content = []
                    for tu in tool_uses:
                        tool_id = tu.get("id")
                        tool_name = tu.get("name")
                        tool_input = tu.get("input", {})
                        logger.info(
                            f"[TOOL-USE] turno={turno} tool={tool_name} input={str(tool_input)[:200]}"
                        )
                        result_str = execute_tool(tool_name, tool_input)
                        tool_results_content.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": result_str,
                            }
                        )
                    messages.append({"role": "user", "content": tool_results_content})
                    continue

                # Sin más tool calls — Claude entregó el dictamen final
                texto_final = ""
                for b in contenido:
                    if b.get("type") == "text":
                        texto_final += b.get("text", "")
                if not texto_final:
                    raise RuntimeError("Tool use terminó sin texto final")
                logger.info(f"[TOOL-USE] dictamen final tras {turno + 1} turnos")
                return texto_final, f"anthropic/{modelo_efectivo}/tools"

        # Llegamos a max_turns sin texto final
        raise RuntimeError(f"Tool use no convergió en {max_turns} turnos")

    async def _llamar_anthropic_multimodal(
        self,
        system: str,
        user: str,
        pdfs_raw: list[tuple[str, bytes]],
    ) -> tuple[str, str]:
        """Llama a Claude pasándole el user prompt + los PDFs de soportes
        como `document` content blocks (formato nativo Anthropic).

        Solo se usa cuando `data.usar_pdf_nativo_soportes=True`. Permite
        que Claude lea TODAS las páginas de soportes complejos (RIPS con
        tablas, historias clínicas escaneadas, facturas con layout raro)
        sin perder información por errores de pdfplumber/OCR.

        Args:
            system: system prompt completo
            user: user prompt (sin contexto_pdf — los PDFs van por separado)
            pdfs_raw: lista de tuplas (nombre_archivo, bytes_pdf)

        Devuelve (texto_dictamen, etiqueta_modelo).
        """
        import base64
        import httpx

        if not self.anthropic_key:
            raise RuntimeError("Anthropic API key no configurada (multimodal)")
        if not pdfs_raw:
            raise RuntimeError("multimodal sin PDFs adjuntos")

        # Anthropic acepta múltiples documentos por mensaje. Cap a 5
        # para no explotar tokens (cada PDF ~5-30k input tokens).
        pdfs_efectivos = pdfs_raw[:5]
        content_blocks: list[dict] = []
        for nombre, b in pdfs_efectivos:
            if not b or len(b) < 1024:
                continue
            if len(b) > 32 * 1024 * 1024:
                logger.warning(f"[MULTIMODAL] {nombre} excede 32MB, omitido")
                continue
            content_blocks.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(b).decode("ascii"),
                    },
                }
            )
        if not content_blocks:
            raise RuntimeError("multimodal: ningún PDF válido para enviar")
        # El texto del prompt va al final, después de los documentos
        content_blocks.append({"type": "text", "text": user})

        timeout = httpx.Timeout(connect=15.0, read=240.0, write=60.0, pool=10.0)
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json={
                        "model": self.anthropic_model,
                        "max_tokens": 3000,
                        "temperature": 0.10,
                        "system": system,
                        "messages": [{"role": "user", "content": content_blocks}],
                    },
                )
        except Exception as e:
            logger.error(f"[MULTIMODAL] Error red: {e}")
            raise RuntimeError(f"Multimodal falló por red: {e}")

        if resp.status_code != 200:
            logger.error(f"[MULTIMODAL] HTTP {resp.status_code}: {resp.text[:500]}")
            raise RuntimeError(f"Multimodal HTTP {resp.status_code}")

        data = resp.json()
        contenido = data.get("content") or []
        texto_final = ""
        for b in contenido:
            if b.get("type") == "text":
                texto_final += b.get("text", "")
        if not texto_final:
            raise RuntimeError("Multimodal terminó sin texto final")
        logger.info(
            f"[MULTIMODAL] OK con {len(pdfs_efectivos)} PDFs | "
            f"input_tokens={data.get('usage', {}).get('input_tokens', '?')}"
        )
        return texto_final, f"anthropic/{self.anthropic_model}/multimodal"

    async def _llamar_ia(
        self,
        system: str,
        user: str,
        eps: str = "",
        codigo: str = "",
        modelo_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        bypass_cache: bool = False,
        llamada_corta: bool = False,
    ) -> tuple[str, str]:
        """Llama a la IA configurada (primary_ai) con fallback al otro proveedor.

        Orden de consulta de caché:
          1. Caché en memoria (_CACHE_IA, TTL 1h) — rapidísimo
          2. Caché persistente BD (ai_cache, TTL 30 días) — sobrevive reinicios
          3. Llamar a la IA y guardar en ambos cachés

        modelo_override: para forzar un modelo específico (ej. "claude-opus-4-7"
        en casos de alta complejidad). Se propaga al provider Anthropic.
        bypass_cache: para retries de validación (no queremos servir respuestas
        defectuosas desde caché).
        llamada_corta: marca llamadas auxiliares de salida breve (auto-crítica,
        refinamiento, checks pre-radicación). Solo afecta a Groq/gpt-oss:
        reasoning_effort 'low' en vez de 'medium' (fix #9) para no quemar
        presupuesto de razonamiento en tareas simples. No participa en la
        clave de caché (misma semántica de respuesta).
        """
        # Clave de caché incluye EPS, código y modelo override para evitar
        # colisiones cruzadas entre Sonnet/Opus. Bump de versión (ronda 5,
        # 16-jun-2026): añadimos `_PROMPT_CACHE_VERSION` al hash — al cambiar
        # el system prompt, una red final o un sanitizador, basta con bumpear
        # esa constante para invalidar TODOS los cachés viejos. Sin esto el
        # caso 8 vino del caché DB con etiqueta qwen3 vieja aunque ya
        # tuviéramos los fixes desplegados.
        modelo_para_clave = modelo_override or self.anthropic_model
        clave_cache = hashlib.sha256(
            (
                f"{_PROMPT_CACHE_VERSION}|{self.primary_ai}|{modelo_para_clave}|"
                f"{eps}|{codigo}|{system}|{user}"
            ).encode()
        ).hexdigest()

        # 1) Caché en memoria (lock asyncio para evitar race condition con
        #    múltiples requests concurrentes escribiendo la misma clave)
        if not bypass_cache:
            async with _CACHE_IA_LOCK:
                if clave_cache in _CACHE_IA:
                    cached = _CACHE_IA[clave_cache]
                else:
                    cached = None
            if cached is not None:
                if isinstance(cached, tuple):
                    respuesta, modelo = cached[0], cached[1]
                else:
                    respuesta, modelo = cached, "cache"
                logger.info(f"Cache MEM: {len(respuesta)} chars [{modelo}]")
                return respuesta, modelo

            # 2) Caché persistente en BD (si hay sesión global disponible)
            cached_db = _buscar_cache_ia_db(clave_cache)
            if cached_db is not None:
                respuesta, modelo = cached_db
                async with _CACHE_IA_LOCK:
                    _CACHE_IA[clave_cache] = (respuesta, modelo)  # rellenar caché memoria
                logger.info(f"Cache DB: {len(respuesta)} chars [{modelo}]")
                return respuesta, modelo

        logger.info(f"IA: {len(system)} + {len(user)} chars primary={self.primary_ai}")

        if not self.groq and not self.anthropic_key:
            return (
                "<paciente>ERROR</paciente><argumento>API key no configurada</argumento>",
                "error",
            )

        # Orden de intento segun primary_ai configurado por el usuario.
        # RESPETAMOS la decision del usuario: si dice 'groq', va groq primero
        # (no gastar tokens pagos). Solo si tecnicamente falla (timeout,
        # error, rate limit), cae al fallback.
        #
        # Jun-2026 (decision Yesid): la cadena de dictamenes es SOLO
        # Groq + Anthropic. Gemini quedo exclusivamente como lector de
        # PDFs escaneados (pdf_service + pdf_fallback_patch) y NO entra
        # aqui; OpenRouter salio del proyecto.
        def _agregar_fallbacks(intentos: list, ya_incluido: str) -> None:
            """Agrega los proveedores restantes en orden de preferencia."""
            if ya_incluido != "anthropic" and self.anthropic_key:
                intentos.append(("anthropic", self._llamar_anthropic))
            if ya_incluido != "groq" and self.groq:
                intentos.append(("groq", self._llamar_groq_con_retry))

        if modelo_override and self.anthropic_key:
            # modelo_override SIEMPRE va a Anthropic (Opus/Haiku especifico)
            intentos = [("anthropic", self._llamar_anthropic)]
            _agregar_fallbacks(intentos, "anthropic")
        elif self.primary_ai == "anthropic" and self.anthropic_key:
            intentos = [("anthropic", self._llamar_anthropic)]
            _agregar_fallbacks(intentos, "anthropic")
        elif self.primary_ai == "groq" and self.groq:
            # USUARIO ELIGIO GROQ — respetar (no gastar tokens pagos).
            # Fallback: Anthropic (calidad) despues.
            intentos = [("groq", self._llamar_groq_con_retry)]
            _agregar_fallbacks(intentos, "groq")
        else:
            # primary_ai desconocido o sin proveedor disponible para el
            # primary elegido: Groq (gratis/rapido) -> Anthropic (calidad).
            intentos = []
            if self.groq:
                intentos.append(("groq", self._llamar_groq_con_retry))
            if self.anthropic_key:
                intentos.append(("anthropic", self._llamar_anthropic))

        ultimo_error: Exception = RuntimeError("Sin proveedores IA disponibles")
        for nombre, fn in intentos:
            try:
                # Solo Anthropic acepta modelo/temperature override
                if nombre == "anthropic":
                    content, modelo = await fn(
                        system,
                        user,
                        modelo_override=modelo_override,
                        temperature_override=temperature_override,
                    )
                else:
                    # Groq: propagar la marca de llamada corta para que
                    # gpt-oss use reasoning_effort 'low' (fix #9).
                    content, modelo = await fn(system, user, llamada_corta=llamada_corta)
                async with _CACHE_IA_LOCK:
                    _CACHE_IA[clave_cache] = (content, modelo)
                _guardar_cache_ia_db(clave_cache, content, modelo)
                return content, modelo
            except Exception as e:
                ultimo_error = e
                logger.warning(f"IA {nombre} falló: {e}. Intentando siguiente proveedor…")
                continue

        logger.error(f"Todos los proveedores IA fallaron: {ultimo_error}")
        return f"<paciente>ERROR</paciente><argumento>{str(ultimo_error)}</argumento>", "error"


# ─── Caché persistente en BD (optimización #1) ───────────────────────────────
# TTL 30 días. Las funciones abren sesión SQLAlchemy propia para desacoplar
# del request, de modo que fallas de BD NO rompan el análisis (solo degradan
# performance). Si la BD no está disponible, el flujo sigue con el caché en
# memoria + llamada a IA.

_CACHE_IA_TTL_DIAS = 30


def _buscar_cache_ia_db(clave: str) -> tuple[str, str] | None:
    """Busca una respuesta cacheada en BD. Si existe y no expiró, incrementa
    hit_count + actualiza ultimo_hit y la devuelve. Si expiró, la borra."""
    try:
        from datetime import timedelta

        from app.core.tz import a_utc, ahora_utc
        from app.database import SessionLocal
        from app.models.db import AICacheRecord

        db = SessionLocal()
        try:
            r = db.query(AICacheRecord).filter(AICacheRecord.clave == clave).first()
            if not r:
                return None
            if r.creado_en and (ahora_utc() - a_utc(r.creado_en)) > timedelta(
                days=_CACHE_IA_TTL_DIAS
            ):
                db.delete(r)
                db.commit()
                return None
            r.hit_count = (r.hit_count or 0) + 1
            from sqlalchemy.sql import func as _func

            r.ultimo_hit = _func.now()
            db.commit()
            return (r.respuesta, r.modelo or "db-cache")
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"_buscar_cache_ia_db fallo (se ignora): {e}")
        return None


def _guardar_cache_ia_db(clave: str, respuesta: str, modelo: str) -> None:
    """Persiste una respuesta de IA en BD. Si ya existe (carrera), actualiza.

    Trunca respuestas extremadamente grandes (>500KB) para proteger el
    INSERT contra respuestas runaway del LLM. Logea cuando aplica truncado
    para poder investigar el prompt problemático.
    """
    try:
        if respuesta and len(respuesta) > _CACHE_MAX_RESP_LEN:
            logger.warning(
                f"_guardar_cache_ia_db: respuesta truncada de {len(respuesta)} "
                f"a {_CACHE_MAX_RESP_LEN} chars [modelo={modelo}]"
            )
            respuesta = respuesta[:_CACHE_MAX_RESP_LEN]
        from app.database import SessionLocal
        from app.models.db import AICacheRecord

        db = SessionLocal()
        try:
            existente = db.query(AICacheRecord).filter(AICacheRecord.clave == clave).first()
            if existente:
                existente.respuesta = respuesta
                existente.modelo = modelo
            else:
                db.add(AICacheRecord(clave=clave, respuesta=respuesta, modelo=modelo, hit_count=0))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"_guardar_cache_ia_db fallo (se ignora): {e}")
