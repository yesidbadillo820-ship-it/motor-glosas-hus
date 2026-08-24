"""
clausulas_anti_rebatimiento.py — Pre-anulación de contra-argumentos EPS típicos
==============================================================================
Cuando una EPS recibe una respuesta a glosa, típicamente responde con
contra-argumentos predecibles. Este módulo pre-anula los más comunes.

Uso:
    from app.services.clausulas_anti_rebatimiento import clausulas_para_codigo
    extra = clausulas_para_codigo("TA0801")  # → "SIN QUE SEA ADMISIBLE..."
"""

import re

# Contra-argumentos típicos EPS y cláusula de pre-anulación por tipo de glosa
CLAUSULAS_POR_TIPO: dict[str, list[dict]] = {
    "TA": [
        {
            "contra": "La EPS aduce 'interpretación del manual tarifario' para justificar el descuento.",
            "preanulacion": "SIN QUE SEA ADMISIBLE ADUCIR INTERPRETACIÓN UNILATERAL DEL MANUAL TARIFARIO EN VÍA DE GLOSA, PUES ELLO CONTRAVIENE EL PRINCIPIO DE BUENA FE CONTRACTUAL (ART. 871 C.COMERCIO) Y LA FUERZA VINCULANTE DEL CONTRATO (ART. 1602 C.CIVIL).",
        },
        {
            "contra": "La EPS argumenta que el descuento aplicado está 'alineado con el IPC o los indicadores del sector'.",
            "preanulacion": "EL IPC O CUALQUIER INDICADOR MACROECONÓMICO CONSTITUYE MERO REFERENTE QUE NO OBLIGA A LA IPS A REDUCIR TARIFAS CONTRACTUALMENTE PACTADAS.",
        },
        {
            "contra": "La EPS pretende aplicar una tarifa sustitutiva no pactada en el contrato.",
            "preanulacion": "LA SUSTITUCIÓN DE LA TARIFA PACTADA POR OTRA DISTINTA REQUIERE ACUERDO MODIFICATORIO ENTRE LAS PARTES, NO SIENDO PROCEDENTE SU IMPOSICIÓN UNILATERAL EN VÍA DE GLOSA.",
        },
    ],
    "SO": [
        {
            "contra": "La EPS alega que los soportes 'no son legibles' o 'no son suficientes'.",
            "preanulacion": "SIN QUE SEA ADMISIBLE RECHAZAR SOPORTES QUE OBRAN EN EL EXPEDIENTE INSTITUCIONAL BAJO ARGUMENTOS DE LEGIBILIDAD O FORMATO, PUES LA HISTORIA CLÍNICA CONSTITUYE DOCUMENTO MÉDICO-LEGAL DE PLENA PRUEBA (RES. 1995/1999) Y LOS ERRORES FORMALES SON SUBSANABLES (CIRCULAR 030/2013).",
        },
        {
            "contra": "La EPS exige soportes adicionales no contemplados en la Res. 2284/2023.",
            "preanulacion": "LOS SOPORTES EXIGIBLES A LA IPS SON TAXATIVAMENTE LOS SEÑALADOS EN LA RESOLUCIÓN 2284 DE 2023 (MANUAL ÚNICO DE GLOSAS), NO SIENDO ADMISIBLE EXIGIR DOCUMENTACIÓN ADICIONAL NO PREVISTA NORMATIVAMENTE.",
        },
    ],
    "AU": [
        {
            "contra": "La EPS alega que 'no se solicitó autorización previa' pese a ser urgencia.",
            "preanulacion": "LA AUTORIZACIÓN PREVIA NO CONSTITUYE REQUISITO LEGAL EN LA ATENCIÓN DE URGENCIAS (ART. 168 LEY 100/1993; ART. 20 DECRETO 4747/2007), SIENDO LA SOLA CONFIGURACIÓN DEL HECHO VITAL LA QUE ACTIVA LA COBERTURA OBLIGATORIA.",
        },
        {
            "contra": "La EPS argumenta que 'el paciente debió ser remitido a red contratada'.",
            "preanulacion": "NO PUEDE TRASLADARSE A LA IPS LA CARGA DE UN TRÁMITE ADMINISTRATIVO PROPIO DE LA ENTIDAD PAGADORA CUANDO LA CONDICIÓN DEL PACIENTE EXIGE ATENCIÓN INMEDIATA E INDIVISIBLE.",
        },
    ],
    "CO": [
        {
            "contra": "La EPS alega que 'el servicio está excluido del PBS'.",
            "preanulacion": "LAS EXCLUSIONES DEL PLAN DE BENEFICIOS SON TAXATIVAS SEGÚN EL ARTÍCULO 15 DE LA LEY 1751 DE 2015 Y DEBEN ESTAR EXPRESAMENTE LISTADAS, NO SIENDO ADMISIBLE UNA INTERPRETACIÓN RESTRICTIVA.",
        },
        {
            "contra": "La EPS traslada a la IPS la gestión ante ADRES de servicios no PBS.",
            "preanulacion": "LA GESTIÓN DE SERVICIOS NO INCLUIDOS EN EL PBS ANTE LA ADRES ES RESPONSABILIDAD EXCLUSIVA DE LA ENTIDAD PAGADORA CONFORME AL DECRETO 780 DE 2016, NO SIENDO PROCEDENTE SU TRASLADO A LA IPS.",
        },
    ],
    "CL": [
        {
            "contra": "La EPS sostiene que 'el procedimiento no era pertinente según guía clínica'.",
            "preanulacion": "NO SIENDO PROCEDENTE SUSTITUIR EL CRITERIO DEL MÉDICO TRATANTE POR UNA REVISIÓN ADMINISTRATIVA QUE NO EXAMINÓ AL PACIENTE (ART. 17 LEY 1751/2015), LA AUDITORÍA DEBE APORTAR CONTRADICCIÓN CIENTÍFICA CON SUSTENTO CLÍNICO EQUIVALENTE.",
        },
        {
            "contra": "La EPS alega 'falta de indicación clínica' pese a la historia clínica.",
            "preanulacion": "LA HISTORIA CLÍNICA, CON EL VALOR PROBATORIO QUE LE CONFIERE LA RESOLUCIÓN 1995 DE 1999, DOCUMENTA LA INDICACIÓN CLÍNICA CON VALOR DE PLENA PRUEBA, NO SIENDO ADMISIBLE DESCONOCERLA POR REVISIÓN DOCUMENTAL ADMINISTRATIVA.",
        },
    ],
    "PE": [
        {
            "contra": "La EPS sostiene que 'el procedimiento no era pertinente según guía clínica'.",
            "preanulacion": "NO SIENDO PROCEDENTE SUSTITUIR EL CRITERIO DEL MÉDICO TRATANTE POR UNA REVISIÓN ADMINISTRATIVA QUE NO EXAMINÓ AL PACIENTE (ART. 17 LEY 1751/2015).",
        },
    ],
    "FA": [
        {
            "contra": "La EPS alega que el servicio 'está incluido en paquete' o 'duplicado'.",
            "preanulacion": "SIN QUE SEA ADMISIBLE SUBSUMIR EL SERVICIO FACTURADO EN UN PAQUETE CONTRACTUAL QUE NO LO CONTEMPLA, PUES LA NATURALEZA DEL CUPS FACTURADO Y LA HISTORIA CLÍNICA (RES. 1995/1999) ACREDITAN SU INDEPENDENCIA.",
        },
        {
            "contra": "La EPS pretende aplicar la Circular 030/2013 a disputas de naturaleza del servicio.",
            "preanulacion": "LA CIRCULAR 030 DE 2013 APLICA TAXATIVAMENTE A ERRORES FORMALES SUBSANABLES, NO A DISPUTAS SOBRE LA NATURALEZA O EL ALCANCE DEL SERVICIO PRESTADO.",
        },
    ],
    "IN": [
        {
            "contra": "La EPS argumenta que 'los insumos estaban incluidos en el procedimiento'.",
            "preanulacion": "LOS INSUMOS INHERENTES AL ACTO MÉDICO SE FACTURAN CONFORME AL COSTO DE ADQUISICIÓN MÁS PORCENTAJE ADMINISTRATIVO PACTADO (DEC. 780/2016; ART. 871 C.COMERCIO), SIENDO IMPROCEDENTE SUBSUMIRLOS SIN SOPORTE CONTRACTUAL EXPRESO.",
        },
    ],
    "ME": [
        {
            "contra": "La EPS alega que 'el medicamento es No PBS y debe gestionarse por otra vía'.",
            "preanulacion": "LA GESTIÓN DE MEDICAMENTOS NO PBS ANTE LA ADRES ES RESPONSABILIDAD DE LA ENTIDAD PAGADORA (DEC. 780/2016), SIN QUE PUEDA TRASLADARSE A LA IPS QUE DISPENSÓ EN CUMPLIMIENTO DE LA PRESCRIPCIÓN MÉDICA.",
        },
        {
            "contra": "La EPS dice que 'no se aportó evidencia de necesidad clínica'.",
            "preanulacion": "LA FÓRMULA MÉDICA EXPEDIDA POR EL MÉDICO TRATANTE EN EJERCICIO DE SU AUTONOMÍA PROFESIONAL (ART. 17 LEY 1751/2015) ES EVIDENCIA SUFICIENTE DE LA NECESIDAD CLÍNICA, NO SIENDO EXIGIBLE DOCUMENTACIÓN ADICIONAL A LA EXPRESAMENTE ESTABLECIDA EN LA RES. 2284/2023.",
        },
    ],
}


# CLAUSULAS TRANSVERSALES (aplican a cualquier tipo de glosa)
CLAUSULAS_TRANSVERSALES = [
    "LA INTERPRETACIÓN RESTRICTIVA DEL CONTRATO EN PERJUICIO DEL PRESTADOR DE SERVICIOS, SIN SOPORTE DOCUMENTAL EXPRESO, CONTRAVIENE EL PRINCIPIO DE BUENA FE CONTRACTUAL CONSAGRADO EN EL ARTÍCULO 871 DEL CÓDIGO DE COMERCIO.",
    "NO RESULTA PROCEDENTE QUE LA ENTIDAD PAGADORA MODIFIQUE UNILATERALMENTE LOS CRITERIOS DE RECONOCIMIENTO ECONÓMICO SIN ACUERDO MODIFICATORIO FORMAL ENTRE LAS PARTES.",
    "EL SILENCIO DE LA ENTIDAD PAGADORA DENTRO DEL PLAZO ESTABLECIDO EN EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 OPERA A FAVOR DEL PRESTADOR, GENERANDO EL LEVANTAMIENTO TÁCITO DE LA OBJECIÓN.",
]


def clausulas_transversales(max_n: int = 1) -> list[str]:
    """Retorna cláusulas transversales aplicables a cualquier glosa."""
    return CLAUSULAS_TRANSVERSALES[:max_n]


# ── Bifurcación AU (12-jun-2026, ronda 2) ───────────────────────────────
# Evidencia de producción: glosa "TA0201, SO0601, AU0301 ... sin autorización
# previa para procedimiento PROGRAMADO" salió con "LA ATENCIÓN DE URGENCIAS,
# COMO LA PRESTADA, NO REQUIERE AUTORIZACIÓN PREVIA" — la IA copió la
# cláusula AU de urgencias que este módulo inyectaba SIN mirar el supuesto
# fáctico, pisando la bifurcación del SYSTEM_AU (PR #103). La misma regla
# del system aplica aquí: urgencias SOLO si consta en el texto de la glosa.
_PAT_AU_URGENCIAS = re.compile(
    r"URGENCIA|URGENTE|EMERGENCIA|TRIAGE|C[ÓO]DIGO\s+AZUL|REANIMACI[ÓO]N|\bRCP\b",
    re.IGNORECASE,
)
_PAT_AU_ELECTIVO = re.compile(
    r"PROGRAMAD[OA]|ELECTIV[OA]|AMBULATORI[OA]",
    re.IGNORECASE,
)

# Cláusulas AU para el supuesto ELECTIVO/desconocido (caso B del SYSTEM_AU):
# silencio administrativo positivo + la autorización como trámite del
# pagador, NUNCA la afirmación de que la atención fue de urgencias.
_CLAUSULAS_AU_ELECTIVO: list[dict] = [
    {
        "contra": "La EPS alega 'falta de autorización previa' en servicio electivo/programado.",
        "preanulacion": (
            "LA FALTA DE RESPUESTA OPORTUNA DE LA ENTIDAD PAGADORA A LA SOLICITUD DE "
            "AUTORIZACIÓN, EN LOS PLAZOS DE LA RESOLUCIÓN 2284 DE 2023, CONFIGURA "
            "AUTORIZACIÓN POR SILENCIO ADMINISTRATIVO POSITIVO (T-313/2007), SIN QUE LA "
            "FALTA DE AUTORIZACIÓN EXIMA DEL PAGO DEL SERVICIO EFECTIVAMENTE PRESTADO "
            "CON PERTINENCIA MÉDICA."
        ),
    },
    {
        "contra": "La EPS traslada a la IPS el trámite administrativo de autorización.",
        "preanulacion": (
            "NO PUEDE TRASLADARSE A LA IPS LA CARGA DE UN TRÁMITE ADMINISTRATIVO PROPIO "
            "DE LA ENTIDAD PAGADORA: LA AUTORIZACIÓN ES UN TRÁMITE ENTRE PAGADOR Y "
            "AFILIADO, NO UNA CONDICIÓN DE EXISTENCIA DE LA PRESTACIÓN, POR LO QUE "
            "CORRESPONDE VERIFICAR EL TRÁMITE EN LOS SISTEMAS DE LA ENTIDAD ANTES DE "
            "RATIFICAR."
        ),
    },
]


def _clausulas_au_segun_supuesto(texto_glosa: str) -> list[dict]:
    """Bifurcación del SYSTEM_AU aplicada a las cláusulas anti-rebatimiento.

    (A) URGENCIAS consta en el texto Y no se declara programado/electivo →
        cláusulas AU clásicas (urgencia vital, Art. 168 Ley 100).
    (B) Electivo declarado, o supuesto desconocido (texto vacío) → PROHIBIDO
        afirmar urgencias: cláusulas de silencio administrativo positivo.
    """
    t = texto_glosa or ""
    es_urgencias = bool(_PAT_AU_URGENCIAS.search(t)) and not _PAT_AU_ELECTIVO.search(t)
    if es_urgencias:
        return CLAUSULAS_POR_TIPO.get("AU", [])
    return _CLAUSULAS_AU_ELECTIVO


def clausulas_para_codigo(codigo: str, max_clausulas: int = 2, texto_glosa: str = "") -> list[str]:
    """Retorna las cláusulas anti-rebatimiento aplicables a un código de glosa.

    Args:
        codigo: código de glosa (TA0801, AU0301, ...).
        max_clausulas: tope de cláusulas a retornar.
        texto_glosa: texto de la objeción — OBLIGATORIO para que la familia
            AU evalúe el supuesto fáctico (urgencias vs electivo). Si no se
            pasa, AU asume supuesto DESCONOCIDO y usa la defensa electiva
            (la opción conservadora: jamás inventa que fue urgencias).

    Ejemplo:
        clausulas_para_codigo("TA0801", 2)  # → 2 cláusulas TA más relevantes
    """
    prefijo = (codigo or "")[:2].upper()
    if prefijo == "AU":
        cls = _clausulas_au_segun_supuesto(texto_glosa)
    else:
        cls = CLAUSULAS_POR_TIPO.get(prefijo, [])
    return [c["preanulacion"] for c in cls[:max_clausulas]]


def todas_las_clausulas() -> dict[str, list[dict]]:
    """Retorna el diccionario completo para consultas."""
    return CLAUSULAS_POR_TIPO
