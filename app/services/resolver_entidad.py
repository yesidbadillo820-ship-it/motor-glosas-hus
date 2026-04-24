"""Resolución de nombre de entidad/EPS para UI (Ronda 36).

Helper centralizado que la UI y el export DGH usan para mostrar la EPS
correcta en listados. Evita que aparezca 'OTRA / SIN DEFINIR' cuando el
archivo original sí traía el tercero completo.

La función devuelve 2 versiones:
  - `resolver_entidad_mostrar(glosa)` → string corto para celdas de tabla
  - `resolver_entidad_completa(glosa)` → tupla con AN/NA/NIT (usa export_dgh)

Prioridad del nombre corto para UI:
  1. tercero_nombre (nombre comercial limpio, ej. 'FAMISANAR EPS SUBSIDIADO')
  2. eps (institucional, si no está en la lista de genéricos)
  3. 'SIN DEFINIR' como último recurso

Considera 'OTRA / SIN DEFINIR', 'DISPENSARIO MEDICO', 'DIRECCION DE SANIDAD'
etc. como genéricos truncados → los reemplaza con el tercero_nombre si
existe.
"""
from __future__ import annotations

import re
from typing import Optional


# Nombres genéricos/truncados que no identifican bien al pagador.
# Cuando la EPS del registro está en esta lista y hay tercero_nombre, se usa
# el tercero_nombre que viene del archivo original.
GENERICOS = {
    "OTRA / SIN DEFINIR",
    "OTRA",
    "SIN DEFINIR",
    "",
}


# Prefijos truncados comunes en el Excel original (primeros 30-40 chars).
# Si el eps del registro empieza exactamente con uno de estos prefijos Y
# existe un tercero_nombre más largo, preferimos el tercero_nombre.
PREFIJOS_TRUNCADOS = (
    "DISPENSARIO MEDICO",
    "DIRECCION DE SANIDAD",
    "SANIDAD MILITAR",
    "COMPANIA DE SEGUROS",
    "COMPAÑIA DE SEGUROS",
    "SEGUROS MUNDIAL",
)


_PREFIJO_CODIGO = re.compile(r"^\s*([A-Z]\d{5,})\s*[-–]\s*(.+)$")


def _quitar_prefijo_codigo(nombre: str) -> tuple[str, Optional[str]]:
    """Si viene como 'U220181 - FAMISANAR EPS', separa y devuelve ('FAMISANAR EPS', 'U220181').
    Caso contrario, devuelve (nombre, None)."""
    if not nombre:
        return "", None
    m = _PREFIJO_CODIGO.match(nombre)
    if m:
        return m.group(2).strip(), m.group(1).strip()
    return nombre.strip(), None


def resolver_entidad_mostrar(
    eps: Optional[str],
    tercero_nombre: Optional[str] = None,
    eps_codigo: Optional[str] = None,
) -> str:
    """Nombre corto limpio para mostrar en celdas de tabla.

    Parámetros:
      - eps: `GlosaRecord.eps` (puede venir con prefijo de código)
      - tercero_nombre: `GlosaRecord.tercero_nombre` (corto, del archivo original)
      - eps_codigo: `GlosaRecord.eps_codigo` (código interno si lo hay)

    La función es defensiva con None/vacíos.
    """
    eps = (eps or "").strip()
    tercero = (tercero_nombre or "").strip()
    _cod = (eps_codigo or "").strip()

    # Normalizar eps quitando el prefijo si lo trae embebido
    eps_limpio, cod_embebido = _quitar_prefijo_codigo(eps)
    if not _cod and cod_embebido:
        _cod = cod_embebido

    eps_upper = eps_limpio.upper()
    tercero_upper = tercero.upper()

    # Caso 1: EPS es genérico → usar tercero
    if eps_upper in GENERICOS:
        if tercero:
            return tercero
        return "SIN DEFINIR"

    # Caso 2: EPS es prefijo truncado Y tercero es más específico → usar tercero
    if tercero and len(tercero) > len(eps_limpio) + 5:
        for pref in PREFIJOS_TRUNCADOS:
            if eps_upper.startswith(pref) and tercero_upper != eps_upper:
                return tercero

    # Caso 3: ambos existen y coinciden → devolver el más limpio (sin prefijo)
    if eps_limpio and tercero:
        # Si tercero es substring del eps_limpio, significa que eps es más descriptivo
        # Usualmente pasa al revés — eps queda truncado por el ancho del Excel.
        if len(tercero) >= len(eps_limpio):
            return tercero
        return eps_limpio

    # Caso 4: solo eps
    if eps_limpio:
        return eps_limpio

    # Caso 5: solo tercero
    if tercero:
        return tercero

    return "SIN DEFINIR"


def entidad_con_codigo(
    eps: Optional[str],
    tercero_nombre: Optional[str] = None,
    eps_codigo: Optional[str] = None,
) -> str:
    """Versión CON prefijo de código interno (estilo DGH):
      'U220181 - FAMISANAR EPS SUBSIDIADO'.

    Útil para exports donde DGH espera el identificador completo.
    """
    _corto = resolver_entidad_mostrar(eps, tercero_nombre, eps_codigo)
    _cod = (eps_codigo or "").strip()
    if not _cod:
        # Intentar extraer del eps original
        _, cod = _quitar_prefijo_codigo(eps or "")
        if cod:
            _cod = cod
    if _cod:
        return f"{_cod} - {_corto}"
    return _corto
