"""Detector de sub-conceptos dentro de una glosa de un solo código.

Problema (caso real SALUD TOTAL TMS, 30-jun-2026): una glosa con UN código
(AU0301) puede objetar VARIOS conceptos en su texto:

  "(1) la terapia TMS NO está en el PBS; (2) la hospitalización de 22 días
   excede los lineamientos; (3) la atención NO fue autorizada previamente.
   SE APLICA SANCIÓN DEL 10%... Adicionalmente, se objeta la cobertura del
   acompañamiento familiar..."

El motor respondía en BLOQUE y omitía conceptos. En auditoría de cuentas
médicas, **callar sobre un concepto equivale a aceptarlo** → la EPS
descuenta lo no refutado.

Este módulo detecta esos sub-conceptos (numerados o sueltos) para:
  1. Inyectar al prompt una instrucción de refutar CADA UNO por nombre.
  2. Post-validar que el dictamen los aborde todos (warning si omite).

NO confundir con multi-código (multi_codigo.py), que separa cuando hay
varios CÓDIGOS de glosa (AU0301 + TA0201). Aquí es UN código con varios
CONCEPTOS en el texto.
"""

from __future__ import annotations

import re

# Numeración explícita: "(1)", "(2)"; "(I)", "(II)"; "1.", "2)"; etc.
# Captura el marcador para segmentar el texto en sub-conceptos.
_RE_NUMERACION = re.compile(
    r"(?:^|[\s.;])\(?\s*("
    r"\d{1,2}"  # 1, 2, 12
    r"|[ivxIVX]{1,4}"  # I, II, III, IV (romanos)
    r")\s*[)\.\-]\s+",
)

# Marcadores de "concepto adicional suelto" (sin número) que delatan una
# objeción independiente que la EPS suma al final del texto.
_MARCADORES_CONCEPTO_SUELTO = (
    (
        re.compile(r"\bSE\s+APLICA\s+(?:UNA\s+)?SANCI[ÓO]N\b", re.IGNORECASE),
        "sanción aplicada por la EPS",
    ),
    (re.compile(r"\bSE\s+APLICA\s+(?:UNA\s+)?MULTA\b", re.IGNORECASE), "multa aplicada por la EPS"),
    (
        re.compile(r"\bADICIONALMENTE,?\s+SE\s+OBJETA\b", re.IGNORECASE),
        "concepto adicional objetado",
    ),
    (
        re.compile(r"\bSE\s+OBJETA\s+(?:LA\s+|EL\s+)?COBERTURA\b", re.IGNORECASE),
        "objeción de cobertura",
    ),
    (
        re.compile(r"\bDEBI[ÓO]\s+SER\s+REMITID[OA]\b", re.IGNORECASE),
        "objeción de remisión a otra red",
    ),
    (
        re.compile(
            r"\bNO\s+(?:SE\s+)?(?:ENCUENTRA|EST[ÁA])\s+(?:DENTRO\s+DEL?\s+)?PBS\b", re.IGNORECASE
        ),
        "servicio no incluido en el PBS",
    ),
)

# Verbos que abren una objeción concreta (para resumir el sub-concepto).
_RE_PALABRAS_RESUMEN = re.compile(
    r"\b(TMS|ESTIMULACI[ÓO]N\s+MAGN[ÉE]TICA|HOSPITALIZACI[ÓO]N|"
    r"AUTORIZACI[ÓO]N\s+PREVIA|PBS|SANCI[ÓO]N|MULTA|COBERTURA|"
    r"ACOMPA[ÑN]AMIENTO|REMISI[ÓO]N|PERTINENCIA|TARIFA|D[ÍI]AS|"
    r"CONSENTIMIENTO|COTIZACI[ÓO]N|MIPRES)\b",
    re.IGNORECASE,
)

_MAX_RESUMEN_CHARS = 90
_MIN_CONCEPTO_CHARS = 25


def _resumen_concepto(texto: str) -> str:
    """Resumen corto de un sub-concepto: las primeras ~90 chars del
    fragmento, cortando en límite de palabra. Sin inventar contenido.
    """
    t = re.sub(r"\s+", " ", (texto or "").strip())
    if len(t) <= _MAX_RESUMEN_CHARS:
        return t.rstrip(".,;: ")
    corte = t.rfind(" ", 0, _MAX_RESUMEN_CHARS)
    if corte < 30:  # no había espacio razonable → corte duro
        corte = _MAX_RESUMEN_CHARS
    return t[:corte].rstrip(".,;: ") + "…"


def detectar_subconceptos(texto_glosa: str | None) -> list[dict]:
    """Devuelve los sub-conceptos detectados en el texto de la glosa.

    Cada uno: {"id": "1"|"sanción aplicada por la EPS"|..., "resumen": str,
    "texto": str}. Lista vacía si el texto tiene un solo concepto.

    Estrategia: recolecta TODOS los puntos de inicio de concepto —
    numeración explícita (1)(2)(3) Y marcadores sueltos (SANCIÓN,
    ADICIONALMENTE SE OBJETA, cobertura, remisión, no-PBS) — los ordena por
    posición, y segmenta el texto en fragmentos entre marcas consecutivas.
    Así el último numerado NO se traga la sanción que viene después.
    """
    if not texto_glosa:
        return []
    txt = str(texto_glosa)

    # Puntos de inicio: (posicion_texto, posicion_marca_fin, id).
    marcas: list[tuple[int, int, str]] = []

    # Numeración explícita (1)(2)(3) / (I)(II).
    nums = list(_RE_NUMERACION.finditer(txt))
    hay_numeracion = len(nums) >= 2
    pos_ultima_num = nums[-1].start() if hay_numeracion else -1
    if hay_numeracion:
        for m in nums:
            marcas.append((m.start(), m.end(), m.group(1).strip()))

    # Marcadores de concepto suelto. Si la glosa USA numeración, un marcador
    # suelto solo cuenta cuando aparece DESPUÉS de la última numeración —
    # los que caen dentro de un concepto numerado (ej. "NO está en PBS"
    # dentro del concepto (1)) son parte de ese concepto, no uno nuevo.
    for pat, etiqueta in _MARCADORES_CONCEPTO_SUELTO:
        for m in pat.finditer(txt):
            if hay_numeracion and m.start() <= pos_ultima_num:
                continue
            marcas.append((m.start(), m.start(), etiqueta))

    if len(marcas) < 2:
        return []

    # Ordenar por posición y deduplicar marcas muy cercanas (< 15 chars).
    marcas.sort(key=lambda x: x[0])
    marcas_filtradas: list[tuple[int, int, str]] = []
    for mk in marcas:
        if marcas_filtradas and mk[0] - marcas_filtradas[-1][0] < 15:
            continue
        marcas_filtradas.append(mk)

    # Segmentar: cada fragmento va del fin de su marca al inicio de la
    # siguiente marca.
    subconceptos: list[dict] = []
    ids_vistos: set[str] = set()
    for i, (_pos, fin_marca, ident) in enumerate(marcas_filtradas):
        ini = fin_marca
        fin = marcas_filtradas[i + 1][0] if i + 1 < len(marcas_filtradas) else len(txt)
        frag = txt[ini:fin].strip()
        if len(frag) < _MIN_CONCEPTO_CHARS:
            continue
        if ident in ids_vistos:
            continue
        ids_vistos.add(ident)
        subconceptos.append({"id": ident, "resumen": _resumen_concepto(frag), "texto": frag})

    return subconceptos


def bloque_subconceptos_para_prompt(subconceptos: list[dict]) -> str:
    """Construye la instrucción para el user prompt que fuerza a la IA a
    refutar CADA sub-concepto por separado. "" si hay < 2 sub-conceptos.
    """
    if not subconceptos or len(subconceptos) < 2:
        return ""
    lineas = [
        "\n\n═══ SUB-CONCEPTOS DE LA GLOSA (REFUTACIÓN OBLIGATORIA POR CADA UNO) ═══",
        f"La EPS objeta {len(subconceptos)} conceptos distintos en esta glosa. "
        "DEBES refutar CADA UNO por separado y por su nombre — callar sobre un "
        "concepto equivale a ACEPTARLO (la EPS descuenta lo no refutado). "
        "Estructura tu argumento abordando explícitamente:",
    ]
    for i, s in enumerate(subconceptos, 1):
        lineas.append(f"  ({i}) {s['resumen']}")
    lineas.append(
        "NO respondas en bloque genérico: cada concepto necesita su propia "
        "refutación técnica y normativa. Si un concepto es contractualmente "
        "débil y menor (< 5% del valor), podés aceptarlo parcialmente, pero "
        "DECLARÁLO — no lo omitas."
    )
    return "\n".join(lineas)


def auditar_subconceptos_respondidos(
    dictamen: str | None,
    subconceptos: list[dict],
) -> tuple[bool, list[str]]:
    """Verifica que el dictamen aborde cada sub-concepto detectado.

    Heurística: por cada sub-concepto, busca su palabra-clave principal en
    el dictamen. Devuelve (todos_respondidos, lista_omitidos_resumen).
    NO modifica el dictamen — el caller decide re-prompt o aceptar.
    """
    if not dictamen or not subconceptos or len(subconceptos) < 2:
        return True, []

    def _norm(s: str) -> str:
        return (
            s.lower()
            .replace("ó", "o")
            .replace("í", "i")
            .replace("é", "e")
            .replace("á", "a")
            .replace("ú", "u")
        )

    dict_norm = _norm(dictamen)
    omitidos: list[str] = []
    for s in subconceptos:
        # TODAS las palabras-clave del sub-concepto. Está "respondido" si
        # AL MENOS UNA aparece en el dictamen (no solo la primera).
        claves = {_norm(m.group(0)) for m in _RE_PALABRAS_RESUMEN.finditer(s["texto"])}
        if not claves:
            continue
        if not any(c in dict_norm for c in claves):
            omitidos.append(s["resumen"])
    return len(omitidos) == 0, omitidos
