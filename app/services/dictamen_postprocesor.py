"""Post-procesadores del dictamen IA aplicados antes de persistir.

Directiva del coordinador (mayo 2026):
  > "recuerda quitar esa frase de más que estaba saliendo a lo último
  >  de la respuesta y solo dejar hasta donde decía 'SE SOLICITA EL
  >  LEVANTAMIENTO DE LA GLOSA'"

Aunque el system prompt (`glosa_ia_prompts.py:487`) ya prohíbe coda
procesal después del cierre, modelos como Sonnet/Haiku a veces ignoran
la regla y añaden párrafos de "10 días hábiles", "Art. 57 Ley 1438" o
emails institucionales. Este módulo es el guard-rail determinístico
post-IA que garantiza que NINGÚN dictamen salga con esa coda.
"""
from __future__ import annotations

import re

# Ancla: "SE SOLICITA [RESPETUOSAMENTE] [EL RECONOCIMIENTO Y] EL
# LEVANTAMIENTO [ÍNTEGRO] [Y EL X] DE LA GLOSA". Acepta variantes con
# acentos, mayús/minús y palabras intermedias hasta ~80 chars.
_CIERRE_ANCLA = re.compile(
    r"\bSE\s+SOLICITA\b[\s\w,]{0,80}?\bLEVANTAMIENTO\b[\s\w,]{0,80}?\bDE\s+LA\s+GLOSA\b",
    re.IGNORECASE | re.UNICODE,
)

# Caudas conocidas que la IA suele encadenar tras el cierre y deben
# desaparecer (solo registrar para telemetría/debug futura — no se usan
# directamente, el truncado por punto final cubre todos los casos).
_CAUDAS_TIPICAS = (
    "10 DÍAS HÁBILES",
    "ART. 57 LEY 1438",
    "ESCALERA PROCESAL",
    "CONCILIACIÓN",
    "QUEDAMOS ATENTOS",
    "CORDIALMENTE",
    "ATENTAMENTE",
    "EMAIL INSTITUCIONAL",
    "@HUS.GOV.CO",
)


def truncar_despues_de_levantamiento(texto: str) -> str:
    """Recorta todo lo que venga después del cierre canónico del dictamen.

    Comportamiento:
      • Busca la primera ocurrencia de la frase ancla (SE SOLICITA ...
        LEVANTAMIENTO ... DE LA GLOSA).
      • Localiza el siguiente punto a continuación (máximo 200 chars de
        coletilla aceptable, ej. "Y EL RECONOCIMIENTO ÍNTEGRO").
      • Devuelve el texto hasta ese punto inclusive, descartando todo
        lo posterior.
      • Si no encuentra la frase, devuelve el texto sin tocar (la
        validación del prompt seguirá señalándolo en QA).

    Es idempotente: aplicarlo dos veces produce el mismo resultado.
    """
    if not texto or not isinstance(texto, str):
        return texto

    m = _CIERRE_ANCLA.search(texto)
    if not m:
        return texto

    # Buscar el siguiente punto a partir del fin del match. Permitimos
    # hasta 200 chars de continuación legítima ("Y EL RECONOCIMIENTO
    # ÍNTEGRO DEL VALOR PACTADO EN EL ANEXO N° 1 DEL CONTRATO 440...").
    cola = texto[m.end():m.end() + 200]
    rel = cola.find(".")
    if rel == -1:
        # No hay punto cercano: cortamos en el fin del match y añadimos
        # el punto final faltante.
        return texto[:m.end()].rstrip() + "."

    return texto[:m.end() + rel + 1].rstrip()
