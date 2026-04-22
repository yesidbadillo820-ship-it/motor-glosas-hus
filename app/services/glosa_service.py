import os
import re
import hashlib
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import httpx
from cachetools import TTLCache
from groq import AsyncGroq
from app.models.schemas import GlosaInput, GlosaResult
from app.core.logging_utils import logger
from app.services.glosa_ia_prompts import get_system_prompt, build_user_prompt

_CACHE_IA: TTLCache = TTLCache(maxsize=500, ttl=3600)
_CACHE_TTL = 3600

_ERRORES_REINTENTABLES = frozenset([
    "429", "rate", "limit", "timeout", "stream", "idle",
    "timed out", "connection", "503", "502", "reset", "eof",
])

FERIADOS_CO = [
    # 2025
    "2025-01-01","2025-01-06","2025-03-24","2025-04-17","2025-04-18",
    "2025-05-01","2025-06-02","2025-06-23","2025-06-30","2025-07-20",
    "2025-08-07","2025-08-18","2025-10-13","2025-11-03","2025-11-17",
    "2025-12-08","2025-12-25",
    # 2026
    "2026-01-01","2026-01-12","2026-03-23","2026-04-02","2026-04-03",
    "2026-05-01","2026-05-18","2026-06-08","2026-06-15","2026-06-29",
    "2026-07-20","2026-08-07","2026-08-17","2026-10-12","2026-11-02",
    "2026-11-16","2026-12-08","2026-12-25",
    # 2027 (Ley 1393/2010 - puentes psicológicos automáticos)
    "2027-01-01","2027-01-11","2027-03-22","2027-04-01","2027-04-02",
    "2027-05-01","2027-05-17","2027-06-07","2027-06-14","2027-06-28",
    "2027-07-20","2027-08-07","2027-08-16","2027-10-11","2027-11-01",
    "2027-11-15","2027-12-08","2027-12-25",
    # 2028 (estimados - verificar publicado)
    "2028-01-01","2028-01-10","2028-03-20","2028-04-13","2028-04-14",
    "2028-05-01","2028-05-15","2028-06-05","2028-06-12","2028-06-26",
    "2028-07-20","2028-08-07","2028-08-14","2028-10-09","2028-10-30",
    "2028-11-06","2028-11-13","2028-12-08","2028-12-25",
]

# PLAZO LEGAL: 20 días hábiles según Art. 56 Ley 1438 de 2011
# Las glosas extemporáneas son improcedentes, abusivas y no deben disminuir el pago a las IPS
DIAS_HABILES_LIMITE_EXTEMPORANEA = 20

NORMATIVA_COLOMBIA = """
NORMATIVA APLICABLE:
- Ley 100 de 1993: Sistema de Seguridad Social Integral (Art. 168 - Urgencias)
- Ley 1438 de 2011: Reforma al Sistema de Salud (Artículo 56 - Plazo 20 días hábiles para glosas)
- Ley 1751 de 2015: Ley Estatutaria de Salud (Derecho fundamental a la salud)
- Ley 1122 de 2007: Flujo de recursos entre EPS e IPS (Art. 13)
- Decreto 4747 de 2007: Regulaciones sobre glosas y devoluciones (Art. 20 - Conciliación)
- Decreto 780 de 2016: Decreto Único Reglamentario del Sector Salud
- Resolución 2175 de 2015: Procedimiento de conciliación de glosas médicas
- Resolución 3047 de 2008: Anexo Técnico 5 (Procedimiento glosas)
- Resolución 5269 de 2017: Plan de Beneficios en Salud
- Resolución 054 de 2026: Tarifas SOAT Plenas
- Decreto 2423 de 1996: Manual de Tarifas SOAT
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
    "SO_SOPORTES": "ESTRATEGIA SOPORTES: Historia clínica es plena prueba según Res. 1995/1999. Documentos cumplen norma. EPS tuvo 20 días hábiles para objetar (Art. 56 Ley 1438/2011).",
    "AU_AUTORIZACION": "ESTRATEGIA AUTORIZACIÓN: Atención por urgencia vital. No requiere autorización previa. Art. 168 Ley 100/1993 y Resolución 5269/2017.",
    "CO_COBERTURA": "ESTRATEGIA COBERTURA: Servicio dentro del Plan de Beneficios en Salud (Res. 5269/2017). EPS tiene obligación de pago. No hay exclusiones.",
    "CL_PERTINENCIA": "ESTRATEGIA PERTINENCIA: Autonomía médica protegida por Art. 17 Ley 1751/2015. Criterio del médico tratante prevalece. Historia clínica soporta la decisión.",
    "PE_PERTINENCIA": "ESTRATEGIA PERTINENCIA: Autonomía médica protegida por Art. 17 Ley 1751/2015. Criterio del médico tratante prevalece. Historia clínica soporta la decisión.",
    "FA_FACTURACION": "ESTRATEGIA FACTURACIÓN: Error formal no es causal de glosa (Circular 030/2013). Los errores formales son subsanables. La prestación del servicio genera obligación de pago.",
    "IN_INSUMOS": "ESTRATEGIA INSUMOS: Inherentes al acto médico. Se facturan al costo de adquisición más porcentaje administrativo pactado. Factura de compra disponible como soporte.",
    "ME_MEDICAMENTOS": "ESTRATEGIA MEDICAMENTOS: Dispensados bajo fórmula médica. Plan de Beneficios los incluye (Res. 5269/2017). No existe alternativa terapéutica equivalente.",
    "EXT_EXTEMPORANEA": "ESTRATEGIA EXTEMPORÁNEA: Glosa improcedente por extemporaneidad. Art. 56 Ley 1438/2011 establece 20 días hábiles. EPS perdió el derecho a glosar. Estas glosas son abusivas y no pueden disminuir el pago a la IPS."
}

CODIGOS_GLOSA = {
    "TA": "OBJECIÓN POR TARIFA", "SO": "OBJECIÓN POR SOPORTES",
    "AU": "OBJECIÓN POR AUTORIZACIÓN", "CO": "OBJECIÓN POR COBERTURA",
    "CL": "OBJECIÓN POR PERTINENCIA", "PE": "OBJECIÓN POR PERTINENCIA",
    "FA": "OBJECIÓN POR FACTURACIÓN",
    "IN": "OBJECIÓN POR INSUMOS", "ME": "OBJECIÓN POR MEDICAMENTOS",
    "SE": "OBJECIÓN SIN ESPECIFICACIÓN", "EX": "OBJECIÓN EXTEMPORÁNEA"
}

PLANTILLAS_CODIGO = {
}


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
            ngrama = palabras[i:i + tam_ngrama]
            # Contar repeticiones consecutivas
            repes = 1
            j = i + tam_ngrama
            while j + tam_ngrama <= len(palabras) and palabras[j:j + tam_ngrama] == ngrama:
                repes += 1
                j += tam_ngrama
                if repes > max_repeticiones:
                    # ENCONTRAMOS LOOP — truncar en el inicio del bucle
                    truncado = " ".join(palabras[:i + tam_ngrama])
                    # Agregar cierre limpio
                    if not truncado.rstrip().endswith(("."," ")):
                        truncado += "."
                    truncado += " [TEXTO TRUNCADO POR SISTEMA: LA IA ENTRÓ EN BUCLE — REVISAR Y RE-GENERAR]"
                    return truncado
            i += 1
    return texto


_SUAVIZAR_PATTERNS = [
    # Apertura obligatoria: nunca "RESPETUOSAMENTE" en la primera frase
    (r"\bESE\s+HUS\s+RESPETUOSAMENTE\s+NO\s+ACEPTA\b",
     "ESE HUS NO ACEPTA"),

    # ═══ REGISTRO COLOQUIAL → TÉCNICO-JURÍDICO ═══
    # (detectados en respuestas reales que debilitan la defensa)
    (r"\bLAS\s+RAZONES\s+SON\s+CLARAS[:\.,]?",
     "POR LAS SIGUIENTES RAZONES:"),
    (r"\bLO\s+CUAL\s+NO\s+ES\s+V[ÁA]LIDO\b",
     "LO CUAL NO SE AJUSTA AL MARCO CONTRACTUAL"),
    (r"\bA\s+CONVENIENCIA\b",
     "DE MANERA UNILATERAL"),
    (r"\bPAGO\s+COMPLETO\s+DEL\s+VALOR\s+FACTURADO\b",
     "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO"),
    (r"\bEL\s+PAGO\s+COMPLETO\b",
     "EL RECONOCIMIENTO ÍNTEGRO"),
    (r"\bPAGAR\s+COMPLETO\b",
     "RECONOCER ÍNTEGRAMENTE"),
    (r"\bES\s+CLARO\s+QUE\b",
     "RESULTA EVIDENTE QUE"),
    (r"\b(?:SIMPLEMENTE|B[ÁA]SICAMENTE|OBVIAMENTE|CLARAMENTE)\s+",
     ""),
    (r"\bELLA\s+MISMA\s+FIRM[ÓO]\b",
     "SUSCRITO POR LA ENTIDAD PAGADORA"),
    (r"\bQUE\s+LA\s+EPS\s+ELLA\s+MISMA\b",
     "QUE LA ENTIDAD PAGADORA"),
    (r"\bNO\s+EST[ÁA]\s+BIEN\b",
     "NO RESULTA PROCEDENTE"),
    (r"\bNO\s+ES\s+BUENA\s+IDEA\b",
     "NO RESULTA PROCEDENTE"),
    (r"\bEST[ÁA]\s+USANDO\s+UNA\s+TARIFA\s+DIFERENTE\b",
     "APLICA UNA TARIFA DIFERENTE A LA PACTADA"),
    (r"\bSIN\s+APLICAR\s+DICHO\s+DESCUENTO\b",
     "SIN APLICAR EL DESCUENTO CONTRACTUAL CONVENIDO"),

    # Exigir → Solicitar
    (r"\bSE\s+EXIGE\s+EL\s+LEVANTAMIENTO\s+INMEDIATO\s+Y\s+DEFINITIVO\b",
     "SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO"),
    (r"\bSE\s+EXIGE\s+EL\s+LEVANTAMIENTO\s+INMEDIATO\b",
     "SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO"),
    (r"\bSE\s+EXIGE\s+EL\s+LEVANTAMIENTO\b",
     "SE SOLICITA EL LEVANTAMIENTO"),
    (r"\bSE\s+EXIGE\s+EL\s+PAGO\s+[ÍI]NTEGRO\b",
     "SE SOLICITA EL RECONOCIMIENTO ÍNTEGRO"),
    (r"\bSE\s+EXIGE\s+EL\s+RECONOCIMIENTO\b",
     "SE SOLICITA EL RECONOCIMIENTO"),
    (r"\bSE\s+EXIGE\b(?!\s+EL)",
     "SE SOLICITA"),
    # Obligar → establece el deber
    (r"\bOBLIGA\s+A\s+LA\s+ENTIDAD\s+PAGADORA\s+A\s+RECONOCER\b",
     "ESTABLECE EL DEBER DE RECONOCER"),
    (r"\bOBLIGA\s+A\s+LA\s+EPS\s+A\s+RECONOCER\b",
     "ESTABLECE EL DEBER DE RECONOCER"),
    (r"\bOBLIGA\s+A\s+LAS\s+ENTIDADES?\b",
     "ESTABLECE EL DEBER DE LAS ENTIDADES"),
    # Incumplimiento hostil → diferencia susceptible
    (r"\bCONFIGURA\s+UN\s+INCUMPLIMIENTO\s+CONTRACTUAL\s+INJUSTIFICADO\b",
     "CORRESPONDE A UNA DIFERENCIA SUSCEPTIBLE DE SUBSANACIÓN"),
    (r"\bINCUMPLIMIENTO\s+CONTRACTUAL\s+INJUSTIFICADO\b",
     "DIFERENCIA SUSCEPTIBLE DE SUBSANACIÓN"),
    (r"\bAFECTA\s+DIRECTAMENTE\s+EL\s+FLUJO\s+DE\s+RECURSOS\s+DEL\s+HOSPITAL\b",
     "AFECTA EL FLUJO DE RECURSOS INSTITUCIONALES"),
    # Acusaciones
    (r"\bLO\s+CUAL\s+NO\s+SE\s+HA\s+CUMPLIDO\s+EN\s+ESTE\s+CASO\b\.?",
     "SE SOLICITA SU APLICACIÓN EN EL PRESENTE CASO."),
    (r"\bNO\s+FUE\s+RESPETADA\s+POR\s+LA\s+ENTIDAD\s+PAGADORA\b",
     "REQUIERE SU APLICACIÓN CONFORME A LO CONVENIDO"),
    (r"\bNO\s+FUE\s+RESPETADA\s+POR\s+LA\s+EPS\b",
     "REQUIERE SU APLICACIÓN CONFORME A LO CONVENIDO"),
    (r"\bCONSTITUYE\s+UN\s+ACTO\s+ABUSIVO\s+E\s+IMPROCEDENTE\b",
     "AMERITA SER REVISADA"),
    (r"\bCONSTITUYE\s+UN\s+ACTO\s+ABUSIVO\b",
     "AMERITA SER REVISADA"),
    (r"\bACTO\s+ABUSIVO\s+E\s+IMPROCEDENTE\b",
     "OBJECIÓN SUSCEPTIBLE DE CONCILIACIÓN"),
    (r"\bCARECE\s+DE\s+TODO\s+SUSTENTO\s+LEGAL\b",
     "REQUIERE MAYOR SUSTENTO"),
    (r"\bCARECE\s+DE\s+SUSTENTO\s+CONTRACTUAL\s+Y\s+LEGAL\b",
     "REQUIERE MAYOR SUSTENTO CONTRACTUAL Y LEGAL"),
    (r"\bCARECE\s+DE\s+SUSTENTO\b",
     "REQUIERE MAYOR SUSTENTO"),
    # Frases redundantes
    (r"\bSE\s+REFUERZA\s+LA\s+ARGUMENTACI[ÓO]N\s+DE\s+QUE\b",
     "SE RATIFICA QUE"),
]

_FRASES_ROTAS_PATTERNS = [
    (r"RECONOCIMIENTO\s+[ÍI]NTEGRO\s+DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
     "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO"),
    (r"RECONOCIMIENTO\s+DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
     "RECONOCIMIENTO DEL VALOR FACTURADO"),
    (r"VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
     r"VALOR \1 EN EL EXPEDIENTE"),
    (r"FACTURAD[OA]\s+POR\s+VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
     r"FACTURADO SEGÚN CONSTA EN EL EXPEDIENTE"),
    (r"Y\s+RECONOCIDO\s+SOLO\s+POR\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
     "Y RECONOCIDO PARCIALMENTE POR LA ENTIDAD PAGADORA"),
    (r"RETENCI[ÓO]N\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
     "LA DIFERENCIA INDICADA EN EL EXPEDIENTE"),
    (r"\bDE\s+EL\s+VALOR\b",
     "DEL VALOR"),
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
        texto, flags=re.IGNORECASE,
    )
    # Frases rotas (primero, para que el suavizador no sobre-escriba)
    for pat, repl in _FRASES_ROTAS_PATTERNS:
        texto = re.sub(pat, repl, texto, flags=re.IGNORECASE)
    # Tono hostil → conciliador
    for pat, repl in _SUAVIZAR_PATTERNS:
        texto = re.sub(pat, repl, texto, flags=re.IGNORECASE)
    return texto


def generar_texto_aceptacion_total(codigo_glosa: str = "", valor: str = "", servicio: str = "") -> str:
    """Plantilla RE9702 — GLOSA ACEPTADA AL 100%.

    El auditor decidió aceptar la glosa completa. ESE HUS reconoce la
    objeción y aplicará nota crédito. No hay argumento jurídico; es
    una declaración formal de aceptación.
    """
    cod = codigo_glosa or "INDICADO EN EL EXPEDIENTE"
    val = valor if valor and valor.strip() not in ("$ 0.00", "$0.00", "$ 0", "") else "EL VALOR INDICADO EN EL EXPEDIENTE"
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
    codigo_glosa: str = "", valor_objetado: float = 0.0,
    valor_aceptado: float = 0.0, servicio: str = "",
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
    "ESE HUS NO ACEPTA LA RATIFICACIÓN DE LA GLOSA Y MANTIENE LA "
    "RESPUESTA DADA EN EL TRÁMITE DE LA GLOSA INICIAL, LA CUAL SE CONSIDERA "
    "SUFICIENTEMENTE SUSTENTADA. EN ATENCIÓN AL ARTÍCULO 57 DE LA LEY 1438 DE 2011, "
    "EL ARTÍCULO 20 DEL DECRETO 4747 DE 2007 Y LA RESOLUCIÓN 2284 DE 2023 (MANUAL "
    "ÚNICO DE GLOSAS), SE SOLICITA A LA ENTIDAD PAGADORA LA PROGRAMACIÓN DE LA MESA "
    "DE CONCILIACIÓN DE AUDITORÍA MÉDICA Y/O TÉCNICA, CON EL ÁNIMO DE LLEGAR A UN "
    "ACUERDO ENTRE LAS PARTES DENTRO DE LOS TÉRMINOS LEGALES. CUALQUIER INFORMACIÓN AL CORREO ELECTRÓNICO "
    "INSTITUCIONAL: CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO, VENTANILLA "
    "ÚNICA DE LA ESE HUS CARRERA 33 NO. 28-126. NOTA: DE CONFORMIDAD CON EL ARTÍCULO "
    "57 DE LA LEY 1438 DE 2011, DE NO OBTENERSE RESPUESTA A LA GLOSA RATIFICADA EN "
    "LOS TÉRMINOS ESTABLECIDOS, OPERARÁ EL LEVANTAMIENTO TÁCITO DE LA RESPECTIVA "
    "OBJECIÓN."
)


def generar_texto_extemporanea(dias: int) -> str:
    return (
        f"ESE HUS RESPETUOSAMENTE NO ACEPTA LA GLOSA POR CONSIDERARLA EXTEMPORÁNEA. "
        f"CONFORME AL MARCO CONTRACTUAL VIGENTE Y A LA RESOLUCIÓN 3047 DE 2008, EL "
        f"PLAZO APLICABLE PARA QUE LA ENTIDAD PAGADORA FORMULE GLOSAS ES DE 20 DÍAS "
        f"HÁBILES CONTADOS A PARTIR DE LA RECEPCIÓN DE LA FACTURA, CRITERIO "
        f"INSTITUCIONAL ASUMIDO POR LA ESE HUS. AUN APLICANDO EL PLAZO DEL ARTÍCULO "
        f"57 DE LA LEY 1438 DE 2011 (30 DÍAS HÁBILES PARA LA ENTIDAD PAGADORA Y 15 "
        f"DÍAS HÁBILES ADICIONALES PARA LA IPS), SE OBSERVA QUE HAN TRANSCURRIDO "
        f"{dias} DÍAS HÁBILES, LO QUE SUPERA EL PLAZO LEGAL Y CONTRACTUAL. POR LO "
        f"ANTERIOR, Y EN ATENCIÓN AL PRINCIPIO DE BUENA FE CONTRACTUAL (ART. 871 "
        f"CÓDIGO DE COMERCIO; ART. 1602 CÓDIGO CIVIL) Y A LA LEY 1751 DE 2015, SE "
        f"SOLICITA RESPETUOSAMENTE A LA ENTIDAD PAGADORA EL LEVANTAMIENTO DE LA "
        f"GLOSA Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO, EVITANDO ASÍ "
        f"AFECTACIONES AL FLUJO DE RECURSOS DEL HOSPITAL. CUALQUIER INFORMACIÓN AL "
        f"CORREO ELECTRÓNICO INSTITUCIONAL: CARTERA@HUS.GOV.CO."
    )


def _nombre_entidad_para_texto(eps: str) -> str:
    """Sanitiza el nombre de EPS para uso en texto institucional.

    Casos como "OTRA / SIN DEFINIR", "OTRA", "SIN DEFINIR", "SIN CONTRATO"
    se reemplazan por "LA ENTIDAD PAGADORA" / "LA ENTIDAD RESPONSABLE DEL
    PAGO" — una referencia genérica pero técnicamente correcta.
    """
    if not eps:
        return "LA ENTIDAD PAGADORA"
    e = str(eps).upper().strip()
    if any(k in e for k in ("OTRA", "SIN DEFINIR", "SIN CONTRATO", "N/A", "DESCONOCID")):
        return "LA ENTIDAD PAGADORA"
    return f"LA ENTIDAD {e}"


def generar_texto_injustificada(eps: str, codigo: str = "", valor: str = "") -> str:
    """Argumento fijo para glosas de tarifas SIN contrato pactado (RE9602).

    Estructura de 4 párrafos — apertura "GLOSA INJUSTIFICADA POR CONCEPTO DE
    TARIFAS" alineada al código RE9602 del Manual Único. Incluye petición
    conciliadora + reserva de derechos SuperSalud + contacto.
    """
    entidad = _nombre_entidad_para_texto(eps)
    codigo_str = codigo if codigo else "DE TARIFAS"
    valor_str = valor if valor and valor.strip() not in ("$ 0.00", "$0.00", "$ 0", "") else "EL VALOR INDICADO EN EL EXPEDIENTE"

    return (
        f"ESE HUS NO ACEPTA LA GLOSA INJUSTIFICADA POR CONCEPTO DE TARIFAS "
        f"APLICADA POR {entidad} BAJO EL CÓDIGO {codigo_str}, FACTURADA POR "
        f"{valor_str}. "

        f"LA OBJECIÓN NO SE AJUSTA AL MARCO CONTRACTUAL NI NORMATIVO POR LAS "
        f"SIGUIENTES RAZONES: EN PRIMER LUGAR, NO EXISTE CONTRATO PACTADO ENTRE "
        f"LAS PARTES QUE CONTEMPLE UNA TARIFA CONVENIDA DISTINTA A LA DEL MANUAL "
        f"SOAT, POR LO QUE LA FACTURACIÓN SE REALIZÓ BAJO TARIFA SOAT PLENA. "
        f"EN SEGUNDO LUGAR, NO ES ADMISIBLE APLICAR DESCUENTOS UNILATERALES SIN "
        f"SOPORTE CONTRACTUAL. EN TERCER LUGAR, LA GLOSA CARECE DE EVIDENCIA DE "
        f"UNA TARIFA DISTINTA QUE JUSTIFIQUE LA REDUCCIÓN APLICADA. "

        f"DE CONFORMIDAD CON LA RESOLUCIÓN 054 DE 2026 Y EL DECRETO 2423 DE "
        f"1996, EL MANUAL TARIFARIO SOAT RIGE SUPLETORIAMENTE A FALTA DE "
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
        primary_ai: str = "groq",
        anthropic_model: str = "claude-sonnet-4-6",
        groq_model: str = "llama-3.3-70b-versatile",
    ):
        _timeout = httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=5.0)
        self.groq = AsyncGroq(api_key=groq_api_key, timeout=_timeout) if groq_api_key else None
        self.anthropic_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.primary_ai = (primary_ai or "groq").lower()
        self.anthropic_model = anthropic_model or "claude-sonnet-4-6"
        self.groq_model = groq_model or "llama-3.3-70b-versatile"

    async def analizar(
        self,
        data: GlosaInput,
        contexto_pdf: str = "",
        contratos_db: dict = None,
        few_shots: list[str] = None,
    ) -> GlosaResult:
        texto_base = str(data.tabla_excel).strip().upper()

        codigos_detectados = self._extraer_codigos_glosa(texto_base)
        codigo_det = codigos_detectados[0] if codigos_detectados else "N/A"
        if len(codigos_detectados) > 1:
            logger.warning(
                f"Multi-código detectado ({len(codigos_detectados)}): {codigos_detectados}. "
                f"Se procesa solo el primero ({codigo_det})."
            )
        prefijo = codigo_det[:2] if codigo_det and codigo_det != "N/A" else "XX"
        valor_raw = self._extraer_valor(texto_base)

        msg_tiempo, color_tiempo, dias = "Fechas no ingresadas", "bg-slate-500", 0
        if data.fecha_radicacion and data.fecha_recepcion:
            try:
                dias = self._calcular_dias_habiles(str(data.fecha_radicacion), str(data.fecha_recepcion))
                # PLAZO LEGAL: 20 días hábiles según Art. 56 Ley 1438/2011
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
        elif es_tarifa and not tiene_contrato:
            argumento_fijo = generar_texto_injustificada(eps_key, codigo_det, valor_raw)
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
                numeros = _rex.findall(r"\d+", str(valor_raw))
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

        # Ratificación tiene prioridad sobre extemporaneidad: si ya pasamos por
        # respuesta inicial y la EPS ratificó, el flujo legal es ratificación,
        # NO aceptación tácita.
        if modo_resp == "aceptar_total":
            cod_res, desc_res = "RE9702", "GLOSA ACEPTADA AL 100% POR EL PRESTADOR"
        elif modo_resp == "aceptar_parcial":
            cod_res, desc_res = "RE9801", "GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE"
        elif es_ratificacion:
            cod_res, desc_res = "RE9901", "GLOSA RATIFICADA - SE MANTIENE RESPUESTA INICIAL, SE SOLICITA CONCILIACIÓN"
        elif es_extemporanea:
            cod_res, desc_res = "RE9502", "GLOSA NO PROCEDE - ACEPTACIÓN TÁCITA (Art. 56 Ley 1438/2011)"
        elif es_tarifa and not tiene_contrato:
            cod_res, desc_res = "RE9602", "GLOSA INJUSTIFICADA - APORTA EVIDENCIA DE INJUSTIFICACIÓN"
        else:
            cod_res, desc_res = "RE9901", "GLOSA NO ACEPTADA - SUBSANADA EN SU TOTALIDAD"

        plantilla = obtener_plantilla_por_codigo(codigo_det)
        usa_plantilla = plantilla is not None
        arg_limpio = ""
        normas_clave = ""
        modelo_usado = "desconocido"

        if argumento_fijo:
            pac_ia = "N/A"
            arg_ia = _suavizar_tono(argumento_fijo)
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
            system_prompt = get_system_prompt(
                prefijo=prefijo,
                eps=data.eps
            )
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
            cups_verificado = ""
            _m_cups = re.search(
                r"(?:^|\s|[-·,])\s*(\d{4,8}(?:-\d)?)\s*(?:[-·,]|\s+[A-ZÁÉÍÓÚÑ])",
                texto_base,
            )
            if _m_cups:
                cups_verificado = _m_cups.group(1)
            else:
                _m2 = re.search(r"\b(\d{5,6}(?:-\d)?)\b", texto_base)
                if _m2:
                    cups_verificado = _m2.group(1)

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
                tono=getattr(data, "tono", "conciliador") or "conciliador",
            )
            res_ia, modelo_usado = await self._llamar_ia(
                system_prompt, user_prompt, eps=str(data.eps), codigo=codigo_det
            )

            # XML validation retry: si no vino <argumento> en la respuesta,
            # reintentamos UNA vez con un recordatorio explícito del contrato.
            if "<argumento>" not in res_ia:
                logger.warning("IA no devolvió <argumento>; reintentando con recordatorio XML")
                user_retry = user_prompt + (
                    "\n\nRECORDATORIO CRÍTICO: Tu respuesta anterior no incluyó los tags XML "
                    "requeridos. Responde AHORA estrictamente en el formato XML definido "
                    "(<paciente>, <servicio>, <contrato>, <tarifa>, <normas_clave>, "
                    "<argumento>). Ningún texto fuera de los tags."
                )
                try:
                    res_retry, modelo_usado = await self._llamar_ia(
                        system_prompt, user_retry, eps=str(data.eps), codigo=codigo_det
                    )
                    if "<argumento>" in res_retry:
                        res_ia = res_retry
                except Exception as _e:
                    logger.warning(f"Retry IA falló: {_e}")

            razonamiento = self._xml("razonamiento", res_ia, "")
            if razonamiento:
                logger.info(f"IA razonamiento: {razonamiento[:200]}")

            pac_ia = self._xml("paciente", res_ia, "NO IDENTIFICADO")
            servicio_ia = self._xml("servicio", res_ia, "")
            contrato_ia = self._xml("contrato", res_ia, "")
            tarifa_ia = self._xml("tarifa", res_ia, "")
            arg_ia = self._xml("argumento", res_ia, "")
            normas_clave = self._xml("normas_clave", res_ia, "")

            if not arg_ia or arg_ia == res_ia:
                if "<argumento>" in res_ia:
                    start = res_ia.find("<argumento>") + len("<argumento>")
                    end = res_ia.find("</argumento>")
                    arg_ia = res_ia[start:end].strip() if end > start else res_ia
                else:
                    arg_ia = res_ia

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
                arg_ia, flags=re.IGNORECASE,
            )

            # 2) "VALOR DE EL VALOR INDICADO EN EL EXPEDIENTE" (redundancia)
            arg_ia = re.sub(
                r"VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
                r"VALOR INDICADO EN EL EXPEDIENTE",
                arg_ia, flags=re.IGNORECASE,
            )

            # 3) "RETENCIÓN DE EL VALOR" / "RETENCIÓN DE $EL VALOR"
            arg_ia = re.sub(
                r"RETENCI[ÓO]N\s+DE\s+\$?\s*EL\s+VALOR",
                r"RETENCIÓN DEL VALOR",
                arg_ia, flags=re.IGNORECASE,
            )

            # 4) "FACTURADO POR VALOR DE EL VALOR INDICADO..." → "FACTURADO SEGÚN CONSTA..."
            arg_ia = re.sub(
                r"FACTURAD[OA]\s+POR\s+VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)\s+EN\s+EL\s+EXPEDIENTE",
                r"FACTURADO SEGÚN CONSTA EN EL EXPEDIENTE",
                arg_ia, flags=re.IGNORECASE,
            )

            # 5) "RECONOCIMIENTO ÍNTEGRO DEL VALOR DE EL VALOR INDICADO..."
            arg_ia = re.sub(
                r"RECONOCIMIENTO\s+(ÍNTEGRO\s+)?DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+(INDICADO|FACTURADO|OBJETADO)",
                r"RECONOCIMIENTO \1DEL VALOR \2",
                arg_ia, flags=re.IGNORECASE,
            )

            # 6) Preposición "DE EL" → "DEL"
            arg_ia = re.sub(r"\bDE\s+EL\s+VALOR\b", "DEL VALOR", arg_ia, flags=re.IGNORECASE)

            # 7) Terminología Sanidad Militar: "FUERZAS ARMADAS" → "FUERZAS MILITARES"
            arg_ia = re.sub(r"\bFUERZAS\s+ARMADAS\b", "FUERZAS MILITARES", arg_ia, flags=re.IGNORECASE)
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

            # 11) Limpieza minima de PHI: solo conectores o formatos rotos,
            # PERO conservamos nombres y numero de HC porque son base argumental
            # para la defensa ante la entidad pagadora.
            # Nota: si quieres anonimizar para alguna glosa especifica, hazlo
            # manualmente con "Refinar con IA" pidiendo el cambio.

            # 12) Dobles conectores redundantes
            arg_ia = re.sub(
                r"\b(ADICIONALMENTE|ASIMISMO|IGUALMENTE),\s*(POR\s+SU\s+PARTE|EN\s+IDÉNTICO\s+SENTIDO)",
                r"\1",
                arg_ia, flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"\b(POR\s+SU\s+PARTE),\s*(ADICIONALMENTE|ASIMISMO|IGUALMENTE|EN\s+IDÉNTICO\s+SENTIDO)",
                r"\1",
                arg_ia, flags=re.IGNORECASE,
            )

            # 13) Anti-runaway: detectar y truncar bucles de repetición
            # (cuando la IA entra en degenerate state y repite "DEL X DEL X DEL X...")
            arg_ia = _truncar_runaway(arg_ia)

            # 14) Corregir "DISPOSICIONADO" inventado por IA → DISPENSARIO
            arg_ia = re.sub(r"\bDISPOSICIONADO\b", "DISPENSARIO MÉDICO", arg_ia, flags=re.IGNORECASE)

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
                arg_ia, flags=re.IGNORECASE,
            )

            # 16b) Si el texto original de la glosa NO traía un valor numérico,
            # la IA NO debe inventar cifras. Reemplazamos montos específicos.
            _no_hay_valor_original = (not valor_raw) or valor_raw.strip() in ("$ 0.00", "$0.00", "$ 0")
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
                arg_ia, flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"Y\s+RECONOCIDO\s+SOLO\s+POR\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "Y RECONOCIDO PARCIALMENTE POR LA ENTIDAD PAGADORA",
                arg_ia, flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"RETENCI[ÓO]N\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "LA DIFERENCIA INDICADA EN EL EXPEDIENTE",
                arg_ia, flags=re.IGNORECASE,
            )
            arg_ia = re.sub(
                r"RECONOCIMIENTO\s+ÍNTEGRO\s+DEL\s+VALOR\s+DE\s+EL\s+VALOR\s+INDICADO\s+EN\s+EL\s+EXPEDIENTE",
                "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO",
                arg_ia, flags=re.IGNORECASE,
            )

            # 17) TONO INSTITUCIONAL CONCILIADOR + FRASES ROTAS (safety net
            # compartido con el camino de texto fijo). Ver _suavizar_tono.
            arg_ia = _suavizar_tono(arg_ia)

            arg_limpio = arg_ia.replace("<br/>", " ").replace("*", "")
            arg_ia = arg_ia.replace("\n", "<br/>").replace("*", "")

        score = self._calcular_score(tipo_glosa, es_extemporanea, es_ratificacion, tiene_pdf, es_urgencia, es_tarifa, arg_limpio)

        dictamen = self._generar_dictamen_html(
            codigo_det, valor_raw, cod_res, desc_res, arg_ia, data.eps, tipo_glosa,
            numero_factura=data.numero_factura, numero_radicado=data.numero_radicado,
            normas_clave=normas_clave if normas_clave else None,
            servicio=servicio_ia if servicio_ia else None,
            contrato=contrato_ia if contrato_ia else None,
            tarifa=tarifa_ia if tarifa_ia else None
        )

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

        return GlosaResult(
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
            riesgo_ratificacion=riesgo
        )

    def _calcular_score(self, tipo_glosa: str, es_extemporanea: bool, es_ratificacion: bool,
                        tiene_pdf: bool, es_urgencia: bool, es_tarifa: bool,
                        argumento_generado: str = "") -> float:
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
            normas_citadas = len(re.findall(
                r'(LEY\s*\d+|DECRETO\s*\d+|RESOLUCIÓN|RESOLUCIÓN\s*\d+|ART\.\s*\d+|ARTÍCULO\s*\d+|SENTENCIA)',
                argumento_generado.upper()
            ))
            bonus_normas = min(5.0, normas_citadas * 0.5)
            
            bonus_longitud = min(3.0, len(argumento_generado) / 300)
            
            base = min(100.0, base + bonus_normas + bonus_longitud)
            
            if normas_citadas >= 3:
                logger.info(f"Score bonus: {normas_citadas} normas citadas, {len(argumento_generado)} chars")
        
        return round(base, 1)

    def _xml(self, tag: str, texto: str, default: str) -> str:
        m = re.search(fr'<{tag}>(.*?)</{tag}>', texto, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    def _determinar_tipo_glosa(self, prefijo: str, texto: str) -> str:
        texto_lower = texto.lower()
        # 1) Extemporaneidad tiene prioridad absoluta
        if "extempor" in texto_lower or prefijo == "EX":
            return "EXT_EXTEMPORANEA"
        # 2) Si el prefijo del código es explícito, usarlo
        if prefijo == "TA": return "TA_TARIFA"
        elif prefijo == "SO": return "SO_SOPORTES"
        elif prefijo == "AU": return "AU_AUTORIZACION"
        elif prefijo == "CO": return "CO_COBERTURA"
        elif prefijo == "CL": return "CL_PERTINENCIA"
        elif prefijo == "PE": return "CL_PERTINENCIA"  # retrocompatibilidad: PE → CL
        elif prefijo == "FA": return "FA_FACTURACION"
        elif prefijo == "IN": return "IN_INSUMOS"
        elif prefijo == "ME": return "ME_MEDICAMENTOS"
        # 3) Sin código reconocido → detectar por keywords del texto
        #    Orden importa: SOPORTES antes que FACTURACIÓN porque "falta de
        #    soporte" contiene "factura" implícito en muchos casos.
        if any(p in texto_lower for p in [
            "soporte", "historia clínica", "historia clinica", "rips",
            "documento", "anexo", "epicrisis", "firma médica", "firma medica",
            "ordenes médicas", "ordenes medicas", "sin adjuntar", "falta de evidencia",
        ]):
            return "SO_SOPORTES"
        if any(p in texto_lower for p in [
            "tarifa", "liquidación", "liquidacion", "manual tarifario",
            "soat -", "soat menos", "homologación", "homologacion",
            "diferencia en valor", "descuento unilateral", "uvb",
        ]):
            return "TA_TARIFA"
        if any(p in texto_lower for p in [
            "autorización", "autorizacion", "orden previa", "orden de servicio",
            "sin autorización", "sin autorizacion", "urgencia sin autorización",
            "remisión", "remision",
        ]):
            return "AU_AUTORIZACION"
        if any(p in texto_lower for p in [
            "cobertura", "pbs", "plan de beneficios", "no incluido",
            "exclusión", "exclusion", "no pbs", "adres",
        ]):
            return "CO_COBERTURA"
        if any(p in texto_lower for p in [
            "pertinencia", "no pertinente", "indicación clínica", "indicacion clinica",
            "criterio médico", "criterio medico", "autonomía médica",
            "autonomia medica", "no justificado clínicamente",
        ]):
            return "CL_PERTINENCIA"
        if any(p in texto_lower for p in ["insumo", "material", "precio", "prótesis", "protesis", "dispositivo médico", "dispositivo medico"]):
            return "IN_INSUMOS"
        if any(p in texto_lower for p in ["medicamento", "fármaco", "farmaco", "fórmula", "formula", "tocilizumab", "dosis", "vial"]):
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
        m = re.search(r"\$\s*([\d\.,]+)", texto)
        return f"$ {m.group(1)}" if m else "$ 0.00"

    def _calcular_dias_habiles(self, f1, f2):
        try:
            d1 = datetime.strptime(f1[:10], "%Y-%m-%d")
            d2 = datetime.strptime(f2[:10], "%Y-%m-%d")
            dias, curr = 0, d1
            while curr < d2:
                curr += timedelta(days=1)
                if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in FERIADOS_CO:
                    dias += 1
            return dias
        except Exception:
            return 0

    def _generar_dictamen_html(self, codigo: str, valor: str, cod_res: str, desc_res: str,
                               argumento: str, eps: str, tipo: str,
                               numero_factura: Optional[str] = None,
                               numero_radicado: Optional[str] = None,
                               normas_clave: Optional[str] = None,
                               servicio: Optional[str] = None,
                               contrato: Optional[str] = None,
                               tarifa: Optional[str] = None) -> str:
        colores = {
            "TA_TARIFA": "#1e40af", "SO_SOPORTES": "#7c3aed", "AU_AUTORIZACION": "#059669",
            "CO_COBERTURA": "#dc2626", "CL_PERTINENCIA": "#d97706", "PE_PERTINENCIA": "#d97706",
            "FA_FACTURACION": "#0891b2",
            "IN_INSUMOS": "#e11d48", "ME_MEDICAMENTOS": "#4f46e5", "EXT_EXTEMPORANEA": "#991b1b",
            "RATIFICADA": "#7c3aed", "EXTEMPORANEA": "#991b1b"
        }
        color = colores.get(tipo, "#1e3a8a")

        fila_trazabilidad = ""
        if numero_factura or numero_radicado:
            fila_trazabilidad = f"""
            <tr>
                <td colspan="3" style="padding:6px 10px;font-size:10px;color:#64748b;border-top:1px dashed #e2e8f0;">
                    {'N° Factura: <b>' + numero_factura + '</b>' if numero_factura else ''}
                    {'&nbsp;&nbsp;|&nbsp;&nbsp;' if numero_factura and numero_radicado else ''}
                    {'N° Radicado: <b>' + numero_radicado + '</b>' if numero_radicado else ''}
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
                        {''.join(filas_adj)}
                    </tbody>
                </table>
            </div>"""

        # Bloque metadatos JSON oculto — legible por parsers EPS automatizados
        import json as _json
        from datetime import datetime as _dt
        metadatos = {
            "prestador_nit": "900006037-4",
            "prestador_nombre": "ESE HOSPITAL UNIVERSITARIO DE SANTANDER",
            "codigo_glosa": codigo,
            "valor_objetado": valor,
            "codigo_respuesta": cod_res,
            "eps": eps,
            "numero_factura": numero_factura or "",
            "numero_radicado": numero_radicado or "",
            "tipo_glosa": tipo,
            "fecha_respuesta": _dt.now().strftime("%Y-%m-%d"),
            "marco_normativo": "Res. 2284/2023 Manual Único + Ley 1438/2011 Art. 57",
        }
        bloque_metadatos = (
            '<div style="display:none" data-metadatos-eps="1">'
            f'<script type="application/json">{_json.dumps(metadatos, ensure_ascii=False)}</script>'
            '</div>'
        )

        # QR CODE con trazabilidad del expediente (ITEM #17)
        # Genera un QR que codifica el JSON de metadatos — escaneable desde PDF
        bloque_qr = ""
        try:
            import qrcode as _qr
            import io as _io, base64 as _b64
            qr_payload = _json.dumps({
                "nit": "900006037-4",
                "fac": numero_factura or "",
                "rad": numero_radicado or "",
                "cod": codigo,
                "res": cod_res,
                "fec": _dt.now().strftime("%Y-%m-%d"),
            }, ensure_ascii=False)
            img = _qr.make(qr_payload, box_size=4, border=2)
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            qr_b64 = _b64.b64encode(buf.getvalue()).decode("ascii")
            bloque_qr = (
                '<div style="margin-top:12px;padding:10px;background:#f8fafc;border:1px dashed #cbd5e1;border-radius:8px;display:flex;align-items:center;gap:12px;">'
                f'<img src="data:image/png;base64,{qr_b64}" alt="QR trazabilidad" style="width:96px;height:96px;background:white;padding:4px;border-radius:6px;"/>'
                '<div style="flex:1;font-size:10px;color:#64748b;line-height:1.5;">'
                '<b style="color:#1e40af;display:block;margin-bottom:3px;">📲 TRAZABILIDAD DIGITAL</b>'
                'Código QR con metadatos de la respuesta para radicación digital ante la EPS y consulta ante la SuperSalud. '
                'Contiene NIT prestador, factura, radicado, código de glosa, código de respuesta y fecha.'
                '</div></div>'
            )
        except Exception:
            pass

        # CARÁTULA INSTITUCIONAL (ITEM #12) — solo datos de la IPS, sin firma RL
        bloque_caratula = (
            '<div style="margin-top:20px;padding:14px 18px;background:linear-gradient(135deg,#fafbfc 0%,#fff 100%);border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 1px 2px rgba(15,23,42,.04);">'
            '<div style="text-align:center;">'
            '<div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;">Institución Prestadora de Servicios de Salud</div>'
            '<div style="font-weight:700;color:#0f172a;font-size:13px;">E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER</div>'
            '<div style="font-size:11px;color:#334155;margin-top:2px;">NIT 900.006.037-4 | Res. Habilitación 002145/2015</div>'
            '<div style="font-size:11px;color:#334155;">Carrera 33 No. 28-126, Bucaramanga | Tel. (607) 691 2010</div>'
            '</div>'
            '<div style="margin-top:12px;padding-top:10px;border-top:1px solid #e2e8f0;font-size:10px;color:#64748b;text-align:center;">'
            'Documento generado electrónicamente con validación normativa. '
            f'Fecha de emisión: {_dt.now().strftime("%d/%m/%Y %H:%M")} · '
            'Marco legal: Resolución 2284 de 2023 (Manual Único) — Ley 1438 de 2011 Art. 57'
            '</div>'
            '</div>'
        )

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
                <span style="background:#fef3c7;color:#92400e;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:600;">{tipo.replace('_', ' ')}</span>
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
            hallazgos.append({"nivel": "error", "mensaje": "El argumento es muy corto (menos de 200 caracteres)"})

        # Placeholders típicos olvidados
        placeholders = ["{EPS}", "{NOMBRE}", "{VALOR}", "XXXX", "[INSERTAR", "[COMPLETAR", "TODO:", "N/A NO APLICA"]
        for ph in placeholders:
            if ph in txt.upper():
                hallazgos.append({"nivel": "error", "mensaje": f"Dictamen contiene placeholder sin rellenar: {ph}"})

        # EPS mencionada
        if eps and eps.upper() not in txt.upper() and "ESE HUS" in txt.upper():
            # No critico pero vale warning
            hallazgos.append({"nivel": "warn", "mensaje": f"El texto no menciona explícitamente a {eps}"})

        # Número de factura
        if numero_factura and numero_factura not in txt:
            hallazgos.append({"nivel": "warn", "mensaje": f"No se encuentra el número de factura ({numero_factura}) en el texto"})

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
            hallazgos.append({
                "nivel": "warn",
                "mensaje": f"No se cita ninguna norma típica para glosas {prefijo} ({', '.join(normas_esperadas)})",
            })

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
            hallazgos.append({
                "nivel": "warn",
                "mensaje": f"La glosa tiene {dias_habiles} días hábiles (extemporánea) pero no se argumenta como tal",
            })

        # 2. Validación normativa contra catálogo
        from app.services.normativa import validar_citas
        val_citas = validar_citas(txt)
        for d in val_citas["derogadas"]:
            msg = f"Cita derogada/confusa: {d['cita']}. {d['razon']}"
            if d.get("reemplaza_por"):
                msg += f" → usar {d['reemplaza_por']}"
            hallazgos.append({"nivel": "error", "mensaje": msg})
        if val_citas["no_catalogadas"]:
            hallazgos.append({
                "nivel": "info",
                "mensaje": f"Citas no verificadas (pueden ser válidas): {', '.join(val_citas['no_catalogadas'][:5])}",
            })

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
                res_ia, _modelo = await self._llamar_ia(
                    system_check, user_check, eps=eps, codigo=codigo_glosa
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
            else (f"{errores} error(es), {warnings_} advertencia(s)" if hallazgos else "Sin observaciones")
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
                out["hallazgos"].append({
                    "nivel": m.group(1).lower(),
                    "mensaje": m.group(2).strip()[:300],
                })
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
            "ESE HUS NO ACEPTA",                    # tarifas/facturacion/IA normal
            "ESE HUS RESPETUOSAMENTE",              # ratificadas (legacy, antes del cambio)
            "ESE HUS RECHAZA",                      # Salud Total
            "ESE HUS NO COMPARTE",                  # variante ratificada
        )
        for marker in markers_inicio:
            if marker in txt:
                # Si el marker aparece cerca del inicio (primeros 500 chars), cortamos por alli.
                # Si aparece mas adentro, significa que ya estamos DENTRO del argumento y lo dejamos.
                pos = txt.find(marker)
                if pos < 500:
                    # Para "ARGUMENTACIÓN JURÍDICA" y "RESPUESTA A GLOSA" son labels,
                    # cortamos DESPUES del marker.
                    if marker in ("ARGUMENTACIÓN JURÍDICA", "ARGUMENTACION JURIDICA", "RESPUESTA A GLOSA"):
                        txt = txt[pos + len(marker):].strip()
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
            'PRESTADOR_NIT',        # JSON de metadatos embebido
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

        # Usa _llamar_ia para respetar PRIMARY_AI (Groq o Anthropic)
        content, _modelo = await self._llamar_ia(system, user, eps=eps, codigo=codigo)
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

    async def _llamar_groq_con_retry(self, system: str, user: str, max_intentos: int = 4) -> tuple[str, str]:
        """Llama a Groq con retry exponencial para manejar rate limits y timeouts."""
        ultimo_error: Exception = Exception("Groq: sin intentos")
        
        for intento in range(max_intentos):
            try:
                resp = await self.groq.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    # Modelo configurable via env GROQ_MODEL (default: llama-3.3-70b-versatile).
                    # Llama 3.3 es mas estable que gpt-oss-120b (que entraba en loops
                    # degenerativos repitiendo frases). gpt-oss es mas rapido/barato pero
                    # menos predecible.
                    model=self.groq_model,
                    temperature=0.2,
                    # 3000 tokens son suficientes para argumentos de 500-700 palabras.
                    max_tokens=3000,
                    # Penalización de frecuencia/presencia evita que el modelo
                    # repita palabras/frases (anti-runaway degenerativo).
                    frequency_penalty=0.3,
                    presence_penalty=0.2,
                    timeout=120.0,
                )
                content = resp.choices[0].message.content
                return content, f"groq/{self.groq_model}"
            except Exception as e:
                ultimo_error = e
                error_msg = str(e).lower()
                es_reintentable = any(k in error_msg for k in _ERRORES_REINTENTABLES)
                if es_reintentable and intento < max_intentos - 1:
                    espera = min(2 ** intento, 16)
                    logger.warning(f"Groq error reintentarable: {e}, reintento {intento + 2}/{max_intentos} en {espera}s")
                    await asyncio.sleep(espera)
                    continue
                raise
        raise ultimo_error

    async def _llamar_anthropic(self, system: str, user: str) -> tuple[str, str]:
        """Llama a Claude vía API REST. Devuelve (texto, etiqueta_modelo)."""
        if not self.anthropic_key:
            raise RuntimeError("Anthropic API key no configurada")
        _timeout_anthropic = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=_timeout_anthropic) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.anthropic_model,
                    "max_tokens": 4000,
                    "temperature": 0.15,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            data = resp.json()
            if "content" in data and data["content"]:
                return data["content"][0]["text"], f"anthropic/{self.anthropic_model}"
            # Respuestas de error de la API traen "error": {...}
            err = data.get("error", {}).get("message", str(data)[:300])
            raise RuntimeError(f"Anthropic devolvió sin 'content': {err}")

    async def _llamar_ia(self, system: str, user: str, eps: str = "", codigo: str = "") -> tuple[str, str]:
        """Llama a la IA configurada (primary_ai) con fallback al otro proveedor."""
        # Clave de caché incluye EPS y código para evitar colisiones cruzadas
        clave_cache = hashlib.sha256(
            f"{self.primary_ai}|{self.anthropic_model}|{eps}|{codigo}|{system}|{user}".encode()
        ).hexdigest()

        if clave_cache in _CACHE_IA:
            cached = _CACHE_IA[clave_cache]
            if isinstance(cached, tuple):
                respuesta, modelo = cached[0], cached[1]
            else:
                respuesta, modelo = cached, "cache"
            logger.info(f"Cache: usando respuesta guardada ({len(respuesta)} chars) [{modelo}]")
            return respuesta, modelo

        logger.info(f"IA: {len(system)} + {len(user)} chars primary={self.primary_ai}")

        if not self.groq and not self.anthropic_key:
            return "<paciente>ERROR</paciente><argumento>API key no configurada</argumento>", "error"

        # Orden de intento según configuración
        if self.primary_ai == "anthropic" and self.anthropic_key:
            intentos = [("anthropic", self._llamar_anthropic)]
            if self.groq:
                intentos.append(("groq", self._llamar_groq_con_retry))
        else:
            intentos = []
            if self.groq:
                intentos.append(("groq", self._llamar_groq_con_retry))
            if self.anthropic_key:
                intentos.append(("anthropic", self._llamar_anthropic))

        ultimo_error: Exception = RuntimeError("Sin proveedores IA disponibles")
        for nombre, fn in intentos:
            try:
                content, modelo = await fn(system, user)
                _CACHE_IA[clave_cache] = (content, modelo)
                return content, modelo
            except Exception as e:
                ultimo_error = e
                logger.warning(f"IA {nombre} falló: {e}. Intentando siguiente proveedor…")
                continue

        logger.error(f"Todos los proveedores IA fallaron: {ultimo_error}")
        return f"<paciente>ERROR</paciente><argumento>{str(ultimo_error)}</argumento>", "error"
