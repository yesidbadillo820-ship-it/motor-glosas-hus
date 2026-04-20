"""Catálogo de normativa colombiana vigente para glosas médicas.

Se usa para validar que los argumentos citen normas existentes y vigentes,
y señalar cuando alguien cita una derogada o inexistente.
"""
from __future__ import annotations

# Normas vigentes (2026). El formato de key es "LEY|DECRETO|RES|CIRC|ART|SENT + número"
# Valor: {nombre, resumen, tipo, ambito, vigente, reemplaza_a?}
NORMAS_VIGENTES: dict[str, dict] = {
    # Leyes
    "LEY 100/1993": {
        "nombre": "Ley 100 de 1993",
        "resumen": "Sistema General de Seguridad Social en Salud. Art. 168 sobre atención de urgencias; Art. 177 obligaciones EPS de reconocer valores facturados.",
        "tipo": "LEY", "vigente": True,
    },
    "LEY 1122/2007": {
        "nombre": "Ley 1122 de 2007",
        "resumen": "Flujo de recursos entre EPS e IPS. Art. 13 sobre pagos.",
        "tipo": "LEY", "vigente": True,
    },
    "LEY 1438/2011": {
        "nombre": "Ley 1438 de 2011",
        "resumen": (
            "Reforma al Sistema de Salud. Art. 56: trámite de pagos (anticipo 50%, "
            "facturación dentro de 22 días). "
            "Art. 57: TRÁMITE DE GLOSAS — 30 días hábiles para que la EPS formule "
            "glosas, 15 días hábiles para que la IPS responda. "
            "Art. 126: conflictos ante SuperSalud."
        ),
        "tipo": "LEY", "vigente": True,
    },
    "LEY 1751/2015": {
        "nombre": "Ley 1751 de 2015 (Estatutaria)",
        "resumen": "Ley Estatutaria de Salud. Art. 15 exclusiones excepcionales. Art. 17 autonomía profesional del médico.",
        "tipo": "LEY", "vigente": True,
    },
    # Decretos
    "DECRETO 4747/2007": {
        "nombre": "Decreto 4747 de 2007",
        "resumen": "Regulaciones sobre glosas y devoluciones. Art. 11 documentos de cobro. Art. 20: conciliación.",
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 780/2016": {
        "nombre": "Decreto 780 de 2016 (Decreto Único Reglamentario del Sector Salud)",
        "resumen": (
            "Sección 3 Capítulo 4: marco general de trámite de glosas, flujo de "
            "recursos, plazos de pago y auditoría. PROHÍBE la 'auditoría previa' "
            "como barrera de radicación."
        ),
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 441/2022": {
        "nombre": "Decreto 441 de 2022",
        "resumen": (
            "Actualiza las reglas sobre acuerdos de voluntades (contratos) entre "
            "ERP e IPS. Integra auditoría concurrente y administrativa para "
            "reducir glosas al final del proceso. Seguimiento a la ejecución del "
            "acuerdo de voluntades."
        ),
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 2423/1996": {
        "nombre": "Decreto 2423 de 1996",
        "resumen": "Manual de Tarifas SOAT. Base tarifaria histórica. Actualizado con Circular 025/2024 → UVB 2025.",
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 1795/2000": {
        "nombre": "Decreto 1795 de 2000",
        "resumen": "Sistema de Salud de las Fuerzas Militares y de Policía. Rige contratos Dispensario/Sanidad Militar.",
        "tipo": "DECRETO", "vigente": True,
    },
    "DECRETO 3752/2003": {
        "nombre": "Decreto 3752 de 2003",
        "resumen": "Régimen de salud docentes oficiales — FOMAG.",
        "tipo": "DECRETO", "vigente": True,
    },
    # Resoluciones
    "RESOLUCION 1995/1999": {
        "nombre": "Resolución 1995 de 1999",
        "resumen": "Historia clínica. Documento médico-legal de plena prueba del acto médico.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 3047/2008": {
        "nombre": "Resolución 3047 de 2008",
        "resumen": "Anexo Técnico 5: procedimiento histórico de glosas. Derogada en lo relevante por Res. 2284/2023.",
        "tipo": "RESOLUCION", "vigente": True,  # aún citable como antecedente
    },
    "RESOLUCION 5269/2017": {
        "nombre": "Resolución 5269 de 2017",
        "resumen": "Plan de Beneficios en Salud (PBS). Listado de servicios cubiertos.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 2175/2015": {
        "nombre": "Resolución 2175 de 2015",
        "resumen": "Procedimiento de conciliación de glosas médicas.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 054/2026": {
        "nombre": "Resolución 054 de 2026",
        "resumen": "Tarifas SOAT plenas vigentes 2026 (expresadas en UVB).",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 2284/2023": {
        "nombre": "Resolución 2284 de 2023 (MINSALUD)",
        "resumen": (
            "MANUAL ÚNICO DE DEVOLUCIONES, GLOSAS Y RESPUESTAS — ANEXO TÉCNICO "
            "No. 3. Norma maestra vigente del sistema. Establece causas TAXATIVAS "
            "de glosa (EPS no puede inventar códigos fuera del manual). Códigos "
            "de 6 dígitos: concepto general + específico + aplicación. Define "
            "soportes de cobro obligatorios."
        ),
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 1885/2024": {
        "nombre": "Resolución 1885 de 2024 (MINSALUD)",
        "resumen": (
            "Modifica transitoriedad de la Res. 2284/2023. Implementación "
            "obligatoria por nivel: ALTA COMPLEJIDAD desde 1-feb-2025, MEDIANA "
            "desde 1-abr-2025, BAJA desde 1-jun-2025."
        ),
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 2275/2023": {
        "nombre": "Resolución 2275 de 2023 (MINSALUD)",
        "resumen": (
            "Factura Electrónica de Venta en salud (FEV) y Registros Individuales "
            "de Prestación de Servicios (RIPS). Validación previa ante MinSalud. "
            "Notas crédito/débito electrónicas para ajuste de glosas aceptadas."
        ),
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 866/2021": {
        "nombre": "Resolución 866 de 2021",
        "resumen": "Registros Individuales de Prestación de Servicios de Salud (RIPS). Campos obligatorios.",
        "tipo": "RESOLUCION", "vigente": True,
    },
    "RESOLUCION 5159/2015": {
        "nombre": "Resolución 5159 de 2015",
        "resumen": "Cobertura en salud para población privada de la libertad (PPL). Complemento con Ley 1709/2014.",
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
        "resumen": "Todo contrato legalmente celebrado es ley para las partes.",
        "tipo": "ART", "vigente": True,
    },
    # Sentencias
    "SENTENCIA T-760/2008": {
        "nombre": "Sentencia T-760 de 2008",
        "resumen": "Corte Constitucional — Obligaciones de las EPS en prestación de servicios. NO APLICA a Sanidad Militar ni PPL.",
        "tipo": "SENTENCIA", "vigente": True,
    },
    "SENTENCIA T-1025/2002": {
        "nombre": "Sentencia T-1025 de 2002",
        "resumen": "Urgencias no requieren autorización previa. Aplica transversalmente.",
        "tipo": "SENTENCIA", "vigente": True,
    },
    "SENTENCIA T-478/1995": {
        "nombre": "Sentencia T-478 de 1995",
        "resumen": "Autonomía médica como derecho fundamental protegido.",
        "tipo": "SENTENCIA", "vigente": True,
    },
    # Circulares
    "CIRCULAR 030/2013": {
        "nombre": "Circular 030 de 2013 (MINSALUD)",
        "resumen": "Subsanación de errores formales en facturación. Aplica SOLO a errores formales (no a disputas de naturaleza del servicio).",
        "tipo": "CIRCULAR", "vigente": True,
    },
    "CIRCULAR 025/2024": {
        "nombre": "Circular 025 de 31 de diciembre 2024 (MINSALUD)",
        "resumen": (
            "Actualiza el Manual Tarifario SOAT con UNIDAD DE VALOR BÁSICO (UVB) "
            "desde 01/01/2025. Los valores 2023-2024 estaban en UVT, ahora 2025 "
            "en UVB."
        ),
        "tipo": "CIRCULAR", "vigente": True,
    },
    "CIRCULAR 007/2025": {
        "nombre": "Circular Externa 007 de 2025 (MINSALUD)",
        "resumen": "Cronograma gradual de implementación del Manual Único (Res. 2284/2023) por nivel de complejidad.",
        "tipo": "CIRCULAR", "vigente": True,
    },
    "ACUERDO 002/2001": {
        "nombre": "Acuerdo 002 de 2001 del Consejo Superior de Salud de las Fuerzas Militares",
        "resumen": "Régimen tarifario y cobertura para afiliados del Subsistema de Salud de las FF.MM. Base de contratos con Dispensario Médico.",
        "tipo": "ACUERDO", "vigente": True,
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
    "ART 56 LEY 1438/2011": {
        "razon": (
            "Cita frecuente pero INEXACTA para plazos de glosas. El Art. 56 regula "
            "trámite de pagos. Los plazos de glosas (30 días EPS + 15 días IPS) "
            "están en el Art. 57 Ley 1438/2011."
        ),
        "reemplaza_por": "ART 57 LEY 1438/2011",
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
