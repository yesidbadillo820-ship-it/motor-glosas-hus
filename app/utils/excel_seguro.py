"""Saneo de celdas para exports a Excel (ronda 30).

Dos riesgos al escribir en celdas texto que viene de la EPS o del dictamen:

1. Inyección de fórmulas (CSV/Excel injection): una celda que empieza con
   '=', '+', '-', '@' (o TAB/CR) la interpreta Excel como fórmula al abrir
   el archivo — "=HYPERLINK(...)", "=cmd|...". El texto de una glosa o de
   una observación de la EPS es contenido no confiable.

2. Caracteres de control: openpyxl lanza IllegalCharacterError ante bytes de
   control (0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F) y tumba TODO el documento por
   un solo carácter perdido en cualquier observación.
"""

from __future__ import annotations

import re

# Control chars que openpyxl rechaza (deja pasar \t \n \r).
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_PREFIJOS_FORMULA = ("=", "+", "-", "@")


def sanear_celda_excel(valor):
    """Devuelve el valor seguro para openpyxl.

    - Números/None/bool → tal cual (no son inyectables).
    - Texto → sin caracteres de control y, si empieza con un prefijo de
      fórmula, se antepone un apóstrofo para forzar interpretación literal.
    """
    if valor is None or isinstance(valor, (int, float, bool)):
        return valor
    s = str(valor)
    s = _CTRL_RE.sub("", s)
    if s and s[0] in _PREFIJOS_FORMULA:
        s = "'" + s
    return s
