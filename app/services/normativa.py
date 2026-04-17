"""Catálogo de normativa colombiana vigente para glosas médicas.

Se usa para validar que los argumentos citen normas existentes y vigentes,
y señalar cuando alguien cita una derogada o inexistente.
"""
from __future__ import annotations
from typing import Optional

# Normas vigentes (2026). El formato de key es "LEY|DECRETO|RES|CIRC|ART|SENT + número"
# Valor: {nombre, resumen, tipo, ambito, vigente, reemplaza_a?}
NORMAS_VIGENTES: dict[str, dict] = {
    # Leyes
    "LEY 100/1993": {
        "nombre": "Ley 100 de 1993",
        "resumen": "Sistema General de Seguridad Social en Salud. Art. 168 sobre atención de urgencias.",
        "tipo": "LEY", "vigente": True,
    },
    "LEY 1122/2007": {
        "nombre": "Ley 1122 de 2007",
        "resumen": "Flujo de recursos entre EPS e IPS. Art. 13 sobre pagos.",
        "tipo": "LEY", "vigente": True,
    },
    "LEY 1438/2011": {
        "nombre": "Ley 1438 de 2011",
        "resumen": "Reforma al Sistema de Salud. Art. 56: plazo 20 días hábiles para glosas. Art. 126: conflictos ante SuperSalud.",
        "tipo": "LEY", "vigente": True,
    },
    "LEY 1751/2015": {
        "nombre": "Ley 1751 de 2015 (Estatutaria)",
        "resumen": "Ley Estatutaria de Salud. Art. 17: autonomía profesional del médico.",
        "tipo": "LEY", "vigente": True,
    },
    # Decretos
    "DECRETO 4747/2007": {
        "nombre": "Decreto 4747 de 2007",
        "resumen": "Regulaciones sobre glosas y devoluciones. Art. 20: conciliación.",
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 780/2016": {
        "nombre": "Decreto 780 de 2016",
        "resumen": "Decreto Único Reglamentario del Sector Salud. Compila múltiples normas.",
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 2423/1996": {
        "nombre": "Decreto 2423 de 1996",
        "resumen": "Manual de Tarifas SOAT. Base tarifaria para contratos.",
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 1795/2000": {
        "nombre": "Decreto 1795 de 2000",
        "resumen": "Sistema de Salud de las Fuerzas Militares y Policía.",
        "tipo": "DECRETO", "vigente": True,
    },
    # Resoluciones
    "RESOLUCION 1995/1999": {
        "nombre": "Resolución 1995 de 1999",
        "resumen": "Historia clínica. Plena prueba del acto médico.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 3047/2008": {
        "nombre": "Resolución 3047 de 2008",
        "resumen": "Anexo Técnico 5: procedimiento de glosas.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 5269/2017": {
        "nombre": "Resolución 5269 de 2017",
        "resumen": "Plan de Beneficios en Salud (PBS).",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 2175/2015": {
        "nombre": "Resolución 2175 de 2015",
        "resumen": "Procedimiento de conciliación de glosas médicas.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 054/2026": {
        "nombre": "Resolución 054 de 2026",
        "resumen": "Tarifas SOAT plenas vigentes (2026).",
        "tipo": "RESOLUCION", "vigente": True,
    },
    # Códigos
    "ART 871 C.COMERCIO": {
        "nombre": "Artículo 871 Código de Comercio",
        "resumen": "Principio de buena fe contractual.",
        "tipo": "ART", "vigente": True,
    },
    "ART 1602 C.CIVIL": {
        "nombre": "Artículo 1602 Código Civil",
        "resumen": "Todo contrato es ley para las partes.",
        "tipo": "ART", "vigente": True,
    },
    # Sentencias
    "SENTENCIA T-760/2008": {
        "nombre": "Sentencia T-760 de 2008",
        "resumen": "Corte Constitucional — Obligaciones de las EPS en prestación de servicios.",
        "tipo": "SENTENCIA", "vigente": True,
    },
    "SENTENCIA T-1025/2002": {
        "nombre": "Sentencia T-1025 de 2002",
        "resumen": "Urgencias no requieren autorización previa.",
        "tipo": "SENTENCIA", "vigente": True,
    },
    # Circulares
    "CIRCULAR 030/2013": {
        "nombre": "Circular 030 de 2013",
        "resumen": "Subsanación de errores formales en facturación.",
        "tipo": "CIRCULAR", "vigente": True,
    },
}


# Normas DEROGADAS o confundidas que NO se deben citar
NORMAS_DEROGADAS: dict[str, dict] = {
    "ART 1601 C.CIVIL": {
        "razon": "Posible confusión con Art. 1602 C.Civil (este último es 'ley para las partes'). "
                 "El 1601 trata de otra materia civil no aplicable a glosas.",
        "reemplaza_por": "ART 1602 C.CIVIL",
    },
    "RESOLUCION 5926/2014": {
        "razon": "Referencia dudosa — verificar si se confunde con Res. 5269/2017 (Plan de Beneficios).",
        "reemplaza_por": "RESOLUCION 5269/2017",
    },
    "LEY 1122/2011": {
        "razon": "La Ley 1122 es de 2007, no 2011. La reforma de 2011 es la Ley 1438.",
        "reemplaza_por": "LEY 1438/2011",
    },
}


import re as _re

_PATRONES = [
    (_re.compile(r"\bLEY\s+(\d{2,5})\s+DE\s+(\d{4})", _re.IGNORECASE), "LEY"),
    (_re.compile(r"\bDECRETO\s+(\d{2,5})\s+DE\s+(\d{4})", _re.IGNORECASE), "DECRETO"),
    (_re.compile(r"\bRESOLUCI[ÓO]N\s+(\d{2,5})\s+DE\s+(\d{4})", _re.IGNORECASE), "RESOLUCION"),
    (_re.compile(r"\bCIRCULAR\s+(\d{2,5})\s+DE\s+(\d{4})", _re.IGNORECASE), "CIRCULAR"),
    (_re.compile(r"\bSENTENCIA\s+(T|C|SU)[\s-]?(\d{1,4})\s+DE\s+(\d{4})", _re.IGNORECASE), "SENTENCIA"),
]


def extraer_citas(texto: str) -> list[str]:
    """Extrae todas las citas normativas del texto en formato canónico."""
    if not texto:
        return []
    citas: list[str] = []
    for patron, tipo in _PATRONES:
        for m in patron.finditer(texto):
            if tipo == "SENTENCIA":
                cita = f"SENTENCIA {m.group(1).upper()}-{m.group(2)}/{m.group(3)}"
            else:
                cita = f"{tipo} {m.group(1)}/{m.group(2)}"
            citas.append(cita)
    # También detectar "Art. X" de códigos (aunque sin más contexto no podemos validar)
    return list(dict.fromkeys(citas))  # sin duplicados manteniendo orden


def validar_citas(texto: str) -> dict:
    """Valida las citas del texto contra el catálogo vigente.

    Retorna:
    {
        "citas_encontradas": [...],
        "validas": [...],
        "derogadas": [{"cita": str, "razon": str, "reemplaza_por": str}],
        "no_catalogadas": [...],   # puede ser legítimo (hay muchas normas), solo informativo
        "score_citas": 0-100,
    }
    """
    citas = extraer_citas(texto)
    validas: list[str] = []
    derogadas: list[dict] = []
    no_catalogadas: list[str] = []

    for c in citas:
        if c in NORMAS_VIGENTES:
            validas.append(c)
        elif c in NORMAS_DEROGADAS:
            info = NORMAS_DEROGADAS[c]
            derogadas.append({
                "cita": c,
                "razon": info["razon"],
                "reemplaza_por": info.get("reemplaza_por"),
            })
        else:
            no_catalogadas.append(c)

    total = len(citas) or 1
    score = int(round((len(validas) / total) * 100))
    # Penalizar derogadas fuertemente
    score = max(0, score - len(derogadas) * 20)

    return {
        "citas_encontradas": citas,
        "validas": validas,
        "derogadas": derogadas,
        "no_catalogadas": no_catalogadas,
        "score_citas": score,
    }
