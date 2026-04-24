"""
multi_concepto.py — Detección y manejo de glosas con múltiples códigos
=======================================================================
Cuando una glosa tiene varios códigos (ej. TA0801 + SO0101 + FA0202),
este módulo los detecta y permite generar respuestas separadas coherentes.
"""
from __future__ import annotations
import re


_PATRON_CODIGO = re.compile(r"\b(TA|SO|AU|CO|CL|PE|FA|SE|IN|ME|EX)\d{2,4}\b")


def extraer_todos_los_codigos(texto: str) -> list[str]:
    """Retorna TODOS los códigos de glosa detectados, sin duplicados, en orden."""
    if not texto:
        return []
    # findall con grupos devuelve solo el grupo; usamos finditer para texto completo
    matches = [m.group(0) for m in _PATRON_CODIGO.finditer(texto)]
    vistos: list[str] = []
    for c in matches:
        if c not in vistos:
            vistos.append(c)
    return vistos


def agrupar_por_concepto(codigos: list[str]) -> dict[str, list[str]]:
    """Agrupa códigos por prefijo (concepto)."""
    grupos: dict[str, list[str]] = {}
    for c in codigos:
        pref = c[:2].upper()
        grupos.setdefault(pref, []).append(c)
    return grupos


def detectar_caso_multi_concepto(texto_glosa: str) -> dict:
    """Analiza si el texto es multi-concepto y retorna análisis estructurado.

    Returns:
        {
            "es_multi_concepto": bool,
            "codigos": [str],
            "grupos": {prefijo: [codigos]},
            "num_conceptos": int,
            "recomendacion": str
        }
    """
    codigos = extraer_todos_los_codigos(texto_glosa)
    grupos = agrupar_por_concepto(codigos)

    es_multi = len(grupos) > 1
    num = len(grupos)

    if es_multi:
        conceptos_nombres = {
            "TA": "TARIFAS", "SO": "SOPORTES", "AU": "AUTORIZACIÓN",
            "CO": "COBERTURA", "CL": "PERTINENCIA CLÍNICA",
            "PE": "PERTINENCIA CLÍNICA", "FA": "FACTURACIÓN",
            "IN": "INSUMOS", "ME": "MEDICAMENTOS", "EX": "EXTEMPORÁNEA",
        }
        lista = ", ".join(conceptos_nombres.get(p, p) for p in grupos.keys())
        recomendacion = (
            f"La glosa presenta {num} conceptos distintos ({lista}). "
            "Se recomienda generar una respuesta consolidada que aborde cada concepto "
            "de forma independiente pero con un argumento central coherente."
        )
    else:
        recomendacion = "Glosa de un solo concepto — flujo estándar."

    return {
        "es_multi_concepto": es_multi,
        "codigos": codigos,
        "grupos": grupos,
        "num_conceptos": num,
        "recomendacion": recomendacion,
    }


# ─────────────────────────────────────────────────────────────────────
# DETECTOR DE GLOSAS EN MASA (item #16)
# ─────────────────────────────────────────────────────────────────────

def _normalizar_motivo(texto: str) -> str:
    """Normaliza el motivo de la glosa eliminando detalles específicos."""
    t = (texto or "").upper()
    # Quitar CUPS específicos
    t = re.sub(r"\b\d{5,6}\b", "CUPS", t)
    # Quitar valores monetarios
    t = re.sub(r"\$\s*[\d.,]+", "$VALOR", t)
    # Quitar fechas
    t = re.sub(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", "FECHA", t)
    # Quitar números de factura
    t = re.sub(r"\b\d{4,}\b", "NUM", t)
    # Colapsar espacios
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detectar_glosas_en_masa(glosas: list[dict]) -> list[dict]:
    """Agrupa glosas idénticas o casi idénticas para respuesta consolidada.

    Args:
        glosas: lista de dicts con keys 'codigo', 'eps', 'texto_glosa', 'id'

    Returns:
        Lista de grupos [{firma, count, ids, codigo_ejemplo, eps, texto_ejemplo}]
    """
    if not glosas:
        return []

    grupos: dict[str, list[dict]] = {}
    for g in glosas:
        codigo = (g.get("codigo") or "").upper()
        eps = (g.get("eps") or "").upper().strip()
        motivo = _normalizar_motivo(g.get("texto_glosa", ""))
        firma = f"{eps}|{codigo}|{motivo[:200]}"
        grupos.setdefault(firma, []).append(g)

    resultado = []
    for firma, items in grupos.items():
        if len(items) >= 2:  # solo grupos con 2+ glosas
            primera = items[0]
            resultado.append({
                "firma": firma,
                "count": len(items),
                "ids": [g.get("id") for g in items],
                "codigo_ejemplo": primera.get("codigo"),
                "eps": primera.get("eps"),
                "texto_ejemplo": primera.get("texto_glosa", "")[:200],
                "ahorro_estimado": f"Responder 1 vez en vez de {len(items)}",
            })

    resultado.sort(key=lambda x: x["count"], reverse=True)
    return resultado
