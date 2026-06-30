"""Scorer de dictámenes — tablero de calidad 0–10 (jul-2026).

Codifica la rúbrica EXPERTA de Yesid (auditor de glosas del HUS) como
chequeos DETERMINISTAS (sin LLM, sin costo, reproducibles) sobre el texto
de un dictamen ya generado. Cada defecto resta puntos según su gravedad;
el dictamen parte de 10.

Regla de oro del proyecto:
    Un dictamen es BUENO solo si saca >= 7/10. La IA es "buena" solo si
    TODOS los casos del benchmark sacan >= 7.

Por qué determinista y no LLM-juez: para que sea barato, instantáneo y
que el mismo dictamen saque SIEMPRE el mismo puntaje (memoria/regresión
confiable). Los defectos que Yesid marcó son, casi todos, detectables por
patrón: negar contrato citado, alucinar una norma, dejar un concepto sin
responder, rendirse ante la multa ilegal, tono amenazante, placeholders.

Uso:
    from tests.benchmark.scorer import puntuar_dictamen
    r = puntuar_dictamen(texto_dictamen, caso)
    print(r["score"], r["defectos"])
"""

from __future__ import annotations

import re
import unicodedata

# ── Pesos por gravedad (lo que resta cada defecto) ───────────────────
PESO_CRITICO = (
    3.5  # legal-killer: anula el dictamen (negar contrato, alucinar norma/cláusula, fraude)
)
PESO_ALTO = 2.0  # concepto sin responder, rendirse ante sanción, defensa autodestructiva
PESO_MEDIO = 1.0  # tono, placeholder, muletilla, defensa débil


def _norm(texto: str) -> str:
    """Minúsculas sin tildes para matching robusto."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


# ── Catálogo de normas COMÚNMENTE ALUCINADAS / mal aplicadas ─────────
# (norma citada, contexto donde es INCORRECTA, mensaje). Si el dictamen
# cita la norma Y aparece el contexto equivocado → alucinación.
# Fuente: auditoría experta de Yesid (caso ECOOPSOS: Ley 1388/2010 es de
# CÁNCER infantil, no de discapacidad auditiva).
_NORMAS_ALUCINADAS = [
    (
        r"ley\s+1388\s*(?:de\s*|/)\s*2010",
        r"audit|coclear|hipoacusia|discapacidad\s+auditiva|sordera",
        "Ley 1388/2010 es de CÁNCER infantil, NO de discapacidad auditiva "
        "(correcta: Ley 1618/2013).",
    ),
]


def _check_niega_contrato(dictamen: str, caso: dict) -> list[dict]:
    """CRÍTICO: niega el contrato que la glosa cita (confesión de parte)."""
    if not caso.get("contrato"):
        return []
    d = _norm(dictamen)
    patrones = (
        r"sin\s+contrato\s+pactado",
        r"no\s+exist\w*\s+(?:un\s+)?contrato",
        r"al\s+no\s+existir\s+contrato",
        r"ausencia\s+de\s+contrato",
    )
    for p in patrones:
        m = re.search(p, d)
        if m:
            return [
                {
                    "criterio": "niega_contrato_citado",
                    "gravedad": "CRITICO",
                    "peso": PESO_CRITICO,
                    "evidencia": dictamen[max(0, m.start() - 10) : m.end() + 30],
                }
            ]
    return []


def _check_norma_alucinada(dictamen: str, caso: dict) -> list[dict]:
    """CRÍTICO: cita una norma que no corresponde al tema (alucinación)."""
    d = _norm(dictamen)
    out = []
    for norma_re, ctx_re, msg in _NORMAS_ALUCINADAS:
        if re.search(norma_re, d) and re.search(ctx_re, d):
            out.append(
                {
                    "criterio": "norma_alucinada",
                    "gravedad": "CRITICO",
                    "peso": PESO_CRITICO,
                    "evidencia": msg,
                }
            )
    return out


def _check_clausula_inventada(dictamen: str, caso: dict) -> list[dict]:
    """CRÍTICO: inventa el TEXTO de una cláusula contractual (fraude)."""
    d = _norm(dictamen)
    # "se cita textualmente la cláusula N ... en los términos de" + texto
    # genérico = cita inventada (el motor no tiene el texto real del contrato).
    if re.search(r"cita\s+textualmente\s+la\s+clausula", d) or re.search(
        r"clausula\s+\d+\s+del\s+contrato[^.]{0,40}establece[:\s]+en\s+los\s+terminos\s+de", d
    ):
        return [
            {
                "criterio": "clausula_inventada",
                "gravedad": "CRITICO",
                "peso": PESO_CRITICO,
                "evidencia": "Cita textual inventada de cláusula contractual.",
            }
        ]
    return []


def _check_placeholders(dictamen: str, caso: dict) -> list[dict]:
    """MEDIO: deja rastros de plantilla sin llenar."""
    d = dictamen or ""
    out = []
    patrones = [
        (r"\$x[,\.]?x{2,}", "valor placeholder $x,xxx"),
        # OJO: "en los términos de la Ley/Resolución X" es LEGÍTIMO — es la
        # paráfrasis neutra que el motor usa al descomillar una cita riesgosa
        # (glosa_service _descomillar_citas). Solo se penaliza la versión ROTA:
        # la cláusula INVENTADA con verbo futuro ("...de los servicios de salud
        # SERÁN evaluados..."), señal de plantilla-leak, no de cita real.
        (
            r"en\s+los\s+t[ée]rminos\s+de\s+(?:los|las)\s+[\w\s]{0,40}?(?:ser[áa]n|deber[áa]n|tendr[áa]n|estar[áa]n)\b",
            "muletilla de cláusula inventada ('en los términos de los X serán...')",
        ),
        (r"\bN/A\b.*\bADICIONALMENTE\b.*RECHAZA", "texto inyectado en campo equivocado"),
        (r"\[(?:nombre|valor|fecha|eps|cups)\b", "placeholder [campo]"),
    ]
    for p, msg in patrones:
        if re.search(p, d, re.IGNORECASE):
            out.append(
                {
                    "criterio": "placeholder_sin_llenar",
                    "gravedad": "MEDIO",
                    "peso": PESO_MEDIO,
                    "evidencia": msg,
                }
            )
    return out


def _check_conceptos_sin_responder(dictamen: str, caso: dict) -> list[dict]:
    """ALTO: deja un concepto de la glosa sin responder (silencio = aceptación)."""
    d = _norm(dictamen)
    out = []
    for concepto in caso.get("conceptos", []):
        # cada concepto trae keywords; basta que UNA aparezca para contarlo respondido
        keys = [_norm(k) for k in concepto.get("keywords", [])]
        if keys and not any(k in d for k in keys):
            out.append(
                {
                    "criterio": "concepto_sin_responder",
                    "gravedad": "ALTO",
                    "peso": PESO_ALTO,
                    "evidencia": f"{concepto['id']}: ninguna de {concepto['keywords']}",
                }
            )
    return out


def _check_sancion(dictamen: str, caso: dict) -> list[dict]:
    """ALTO: si la glosa aplica sanción ilegal, el dictamen DEBE rechazarla
    por vicio de competencia — y NO con 'pacta sunt servanda' (que CONCEDE
    que la cláusula aplica). Tiro por la culata detectado por Yesid."""
    if not caso.get("tiene_sancion"):
        return []
    d = _norm(dictamen)
    rechaza = bool(
        re.search(r"vicio\s+de\s+competencia", d)
        or re.search(r"carec\w+\s+de\s+facultad\s+sancionatoria", d)
        or re.search(r"reservad\w+\s+(?:a\s+la\s+)?(?:super)", d)
        or re.search(r"clausula\s+\w*\s*ineficaz|clausula\s+abusiva", d)
    )
    # 'pacta sunt servanda' cerca de la sanción = autodestructivo
    pacta_en_sancion = bool(
        re.search(r"pacta\s+sunt\s+servanda", d)
        and re.search(r"sanci[oó]n|multa", d)
        and not rechaza
    )
    out = []
    if not rechaza:
        out.append(
            {
                "criterio": "sancion_no_rechazada",
                "gravedad": "ALTO",
                "peso": PESO_ALTO,
                "evidencia": "No rechaza la sanción por vicio de competencia (Ley 1438 Art. 126).",
            }
        )
    if pacta_en_sancion:
        out.append(
            {
                "criterio": "sancion_pacta_sunt_servanda",
                "gravedad": "ALTO",
                "peso": PESO_ALTO,
                "evidencia": "Invoca 'Pacta Sunt Servanda' ante la sanción → concede que la cláusula aplica.",
            }
        )
    return out


def _check_silencio_positivo(dictamen: str, caso: dict) -> list[dict]:
    """ALTO: afirma 'silencio = aceptación tácita', falso en el SGSSS."""
    d = _norm(dictamen)
    if re.search(r"silencio\s+(?:como|se\s+entiende|positiv|.{0,20}aceptaci[oó]n\s+tacita)", d):
        return [
            {
                "criterio": "falso_silencio_positivo",
                "gravedad": "ALTO",
                "peso": PESO_ALTO,
                "evidencia": "Afirma silencio = aceptación tácita (incorrecto en SGSSS).",
            }
        ]
    return []


def _check_tono_hostil(dictamen: str, caso: dict) -> list[dict]:
    """MEDIO: tono amenazante rompe la dinámica de conciliación."""
    d = _norm(dictamen)
    patrones = (
        r"cualquier\s+intento\s+de\s+rebatir",
        r"constituir[aá]\s+violaci[oó]n",
        r"generando\s+responsabilidad\s+institucional",
        r"se\s+advierte\s+que",
    )
    for p in patrones:
        if re.search(p, d):
            return [
                {
                    "criterio": "tono_hostil",
                    "gravedad": "MEDIO",
                    "peso": PESO_MEDIO,
                    "evidencia": "Tono amenazante/beligerante en el cierre.",
                }
            ]
    return []


def _check_tarifa_incoherente(dictamen: str, caso: dict) -> list[dict]:
    """ALTO: con contrato citado, exige 'SOAT pleno' (concede el punto de la
    EPS y se apoya en negar el contrato)."""
    if not caso.get("contrato"):
        return []
    d = _norm(dictamen)
    if re.search(r"soat\s+plen", d) and re.search(
        r"no\s+exist\w*\s+contrato|sin\s+contrato|ausencia\s+de\s+contrato", d
    ):
        return [
            {
                "criterio": "tarifa_incoherente",
                "gravedad": "ALTO",
                "peso": PESO_ALTO,
                "evidencia": "Exige SOAT pleno negando el contrato (en vez de defender el factor pactado).",
            }
        ]
    return []


def _check_defensa_clinica(dictamen: str, caso: dict) -> list[dict]:
    """MEDIO: tecnología cara defendida SIN literatura nivel 1A."""
    if not caso.get("es_tecnologia_cara"):
        return []
    d = _norm(dictamen)
    tiene_lit = bool(
        re.search(r"\bfda\b|nice|cochrane|\bwfh\b|\beau\b|\bapa\b|guidelines|nivel\s+1a", d)
    )
    if not tiene_lit:
        return [
            {
                "criterio": "defensa_sin_literatura",
                "gravedad": "MEDIO",
                "peso": PESO_MEDIO,
                "evidencia": "Tecnología cara defendida sin evidencia nivel 1A (FDA/NICE/Cochrane/...).",
            }
        ]
    return []


_CHEQUEOS = (
    _check_niega_contrato,
    _check_norma_alucinada,
    _check_clausula_inventada,
    _check_placeholders,
    _check_conceptos_sin_responder,
    _check_sancion,
    _check_silencio_positivo,
    _check_tono_hostil,
    _check_tarifa_incoherente,
    _check_defensa_clinica,
)

UMBRAL_BUENO = 7.0


def puntuar_dictamen(dictamen: str, caso: dict) -> dict:
    """Puntúa un dictamen 0–10 según la rúbrica experta.

    Returns:
        {score, aprobado, defectos: [...], conteo_por_gravedad}
    """
    defectos: list[dict] = []
    for chequeo in _CHEQUEOS:
        try:
            defectos.extend(chequeo(dictamen, caso))
        except Exception as e:  # un chequeo no debe tumbar el scorer
            defectos.append(
                {
                    "criterio": f"error:{chequeo.__name__}",
                    "gravedad": "MEDIO",
                    "peso": 0.0,
                    "evidencia": str(e),
                }
            )

    penalizacion = sum(d["peso"] for d in defectos)
    score = max(0.0, round(10.0 - penalizacion, 1))
    conteo = {"CRITICO": 0, "ALTO": 0, "MEDIO": 0}
    for d in defectos:
        conteo[d["gravedad"]] = conteo.get(d["gravedad"], 0) + 1
    return {
        "caso": caso.get("id"),
        "score": score,
        "aprobado": score >= UMBRAL_BUENO,
        "defectos": defectos,
        "conteo_por_gravedad": conteo,
    }
