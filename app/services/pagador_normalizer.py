"""Normaliza el nombre de la EPS / entidad pagadora.

El motor recibe el nombre del pagador en varios formatos según la fuente:
  • Plan EPS completo desde DGH: "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG"
  • Tercero comercial corto: "DISPENSARIO MEDICO BUCARAMANGA"
  • Variantes con/sin tilde, mayúsculas inconsistentes, espacios extra.

Sin un normalizador único, distintas vistas (UI de conceptos, prompt al LLM,
PDF, export) pintan formas diferentes y la IA termina generando dictámenes
inconsistentes — el caso real fue glosa #2511 donde un dictamen citó
"DISPENSARIO MEDICO" y otro "U220311 - DIRECCION DE SANIDAD EJERCITO -
DISPENSARIO MEDICO BUCARAMANG" para la misma factura.

Este módulo expone tres formas canónicas:
  • codigo(): solo el código EPS si está embebido (ej. "U220311")
  • nombre_corto(): la marca comercial limpia (ej. "DISPENSARIO MÉDICO BUCARAMANGA")
  • nombre_largo(): forma completa "<código> · <nombre_corto>" para encabezados
"""
from __future__ import annotations

import re
import unicodedata


_RE_CODIGO_EPS = re.compile(r"^([A-Z]\d{6})\s*[-·:]\s*", re.IGNORECASE)
_RE_PREFIJO_DIRECCION = re.compile(
    r"^(DIRECCION|DIRECCIÓN)\s+(DE\s+)?SANIDAD\s+(EJERCITO|EJÉRCITO|"
    r"ARMADA|FUERZA\s+AEREA|FUERZA\s+AÉREA|POLICIA|POLICÍA)\s*[-·:]\s*",
    re.IGNORECASE,
)
_TRUNCADOS = {
    "BUCARAMANG": "BUCARAMANGA",
    "MEDELLI": "MEDELLÍN",
    "MEDELLIN": "MEDELLÍN",
    "BOGOTA": "BOGOTÁ",
}


def _quitar_diacriticos(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _limpiar(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # Colapsar espacios múltiples
    s = re.sub(r"\s+", " ", s)
    return s


def codigo(nombre: str) -> str:
    """Extrae el código EPS si el nombre comienza con uno (ej. 'U220311')."""
    s = _limpiar(nombre).upper()
    m = _RE_CODIGO_EPS.match(s)
    return m.group(1).upper() if m else ""


def nombre_corto(nombre: str) -> str:
    """Devuelve la marca comercial limpia, sin código EPS ni prefijo de dirección.

    Idempotente: nombre_corto(nombre_corto(x)) == nombre_corto(x).
    Repara truncamientos comunes ('BUCARAMANG' → 'BUCARAMANGA').
    """
    s = _limpiar(nombre)
    if not s:
        return ""
    s_upper = s.upper()
    # 1) Quitar código EPS al inicio
    s_upper = _RE_CODIGO_EPS.sub("", s_upper)
    # 2) Quitar prefijo "DIRECCION DE SANIDAD <FUERZA> -" para dejar solo la unidad
    s_upper = _RE_PREFIJO_DIRECCION.sub("", s_upper)
    # 3) Reparar truncamientos comunes (palabras finales recortadas)
    palabras = s_upper.split()
    if palabras and palabras[-1] in _TRUNCADOS:
        palabras[-1] = _TRUNCADOS[palabras[-1]]
    s_upper = " ".join(palabras)
    return s_upper.strip(" -·:")


def nombre_largo(nombre: str) -> str:
    """Forma canónica para encabezados: '<código> · <nombre_corto>'.

    Si no hay código EPS embebido, devuelve solo el nombre corto.
    """
    cod = codigo(nombre)
    corto = nombre_corto(nombre)
    if cod and corto:
        return f"{cod} · {corto}"
    return corto


def son_equivalentes(a: str, b: str) -> bool:
    """True si dos nombres distintos refieren al mismo pagador (matching laxo).

    Útil para deduplicar listas de EPS importadas con grafías distintas.
    """
    if not a or not b:
        return False
    na = _quitar_diacriticos(nombre_corto(a)).upper()
    nb = _quitar_diacriticos(nombre_corto(b)).upper()
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Subsumido: una cadena contiene a la otra y la diferencia es ≤ 6 chars
    if (na in nb or nb in na) and abs(len(na) - len(nb)) <= 6:
        return True
    return False
