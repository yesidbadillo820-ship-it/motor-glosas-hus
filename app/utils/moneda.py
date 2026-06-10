"""Parsing canónico de valores monetarios COP (formato colombiano).

Única fuente de verdad para convertir strings de dinero a float. En
Colombia el punto es separador de MILES y la coma es separador DECIMAL:

    "7.700,00"    → 7700.0      (siete mil setecientos pesos)
    "1.500.000"   → 1500000.0
    "$ 500.000"   → 500000.0

El patrón ingenuo ``float(re.sub(r"[^\\d]", "", x))`` que existía en
varios call sites (analizar.py, glosas.py, schemas.py) convertía
"7.700,00" en 770000 — un error de 100× en los valores persistidos.
Bug detectado el 12-may-2026 en auto_pilot_decision y corregido allí;
esta extracción propaga ese parser correcto al resto del sistema
(auditoría jun-2026, hallazgo P0 #1).

NOTA: la corrección aplica solo a valores NUEVOS. El backfill de filas
históricas en BD es una operación separada (dry-run + snapshot previo).
"""

from __future__ import annotations

import re

__all__ = ["parse_valor_cop"]


def parse_valor_cop(valor_raw) -> float:
    """Convierte string "$1.234.567" / "7.700,00" o número a float COP.

    Reglas (formato colombiano):
      - int/float → float directo; None/vacío/no-numérico → 0.0
      - Prefijos no numéricos ($, COL$, %, espacios) se descartan.
      - Si hay coma con 1-2 dígitos al final → es separador decimal
        ("7.700,00" → 7700.0).
      - Si hay coma con 3+ dígitos detrás → se trata como separador de
        miles y se eliminan todos los símbolos ("1,500,000" → 1500000.0).
      - Sin coma: TODOS los puntos se asumen separadores de miles
        ("1.500.000" → 1500000.0, "1'500.000" → 1500000.0).
    """
    if valor_raw is None:
        return 0.0
    if isinstance(valor_raw, (int, float)):
        return float(valor_raw)
    s = str(valor_raw).strip()
    # Quitar prefijos no numéricos al inicio ($, %, espacios, COL$, etc.)
    s = re.sub(r"^[^\d\-]+", "", s)
    if not s:
        return 0.0
    # Formato colombiano: puntos = miles, coma = decimal ("7.700,00" = 7700.00).
    if "," in s:
        partes = s.rsplit(",", 1)
        enteros = re.sub(r"[^\d\-]", "", partes[0])
        decimales = partes[1].strip()
        if 1 <= len(decimales) <= 2 and decimales.isdigit():
            try:
                return float(f"{enteros}.{decimales}")
            except Exception:
                return 0.0
        # Coma no era decimal (más de 2 dígitos detrás) → todo a entero
        cleaned = re.sub(r"[^\d]", "", s)
        return float(cleaned) if cleaned else 0.0
    # Sin coma: los puntos se asumen separadores de miles (Colombia)
    cleaned = re.sub(r"[^\d]", "", s)
    return float(cleaned) if cleaned else 0.0
