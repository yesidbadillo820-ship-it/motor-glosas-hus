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
# acentos, mayús/minús, puntuación intermedia (—, —, comas, paréntesis)
# y tags HTML hasta ~150 chars entre cada palabra ancla. Usamos [\s\S]
# en vez de [\s\w,] para tolerar cualquier carácter, incluyendo guiones
# largos, comillas tipográficas, y `<br/>` que pueda haber quedado de
# pasos previos del pipeline.
_CIERRE_ANCLA = re.compile(
    r"\bSE\s+SOLICITA\b[\s\S]{0,150}?\bLEVANTAMIENTO\b[\s\S]{0,150}?\bDE\s+LA\s+GLOSA\b",
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
    cola = texto[m.end() : m.end() + 200]
    rel = cola.find(".")
    if rel == -1:
        # No hay punto cercano: cortamos en el fin del match y añadimos
        # el punto final faltante.
        return texto[: m.end()].rstrip() + "."

    return texto[: m.end() + rel + 1].rstrip()


# Lista de citas FRECUENTEMENTE inventadas por Groq llama-3.3 que NO existen
# en el corpus normativo del HUS. Si la IA agrega un párrafo "DE ACUERDO CON..."
# o "EN ESTE SENTIDO..." que mencione ALGUNA de estas, ese párrafo entero se
# elimina. La plantilla del banco HUS ya trae las citas verificadas — la IA
# no necesita inventar más.
_CITAS_INVENTADAS_FRECUENTES = (
    "ART. 10 DE LA LEY 1438",
    "ART. 10 LEY 1438",
    "ARTÍCULO 10 DE LA LEY 1438",
    "ART. 15 DE LA LEY 1122",
    "ART. 15 LEY 1122",
    "ARTÍCULO 15 DE LA LEY 1122",
    "ART. 2 DE LA LEY 1122",
    "ART. 2 LEY 1122",
    "ARTÍCULO 2 DE LA LEY 1122",
    "ART. 14 DE LA LEY 1438",
    "ART. 14 LEY 1438",
    "ARTÍCULO 14 DE LA LEY 1438",
    "ART. 14 DE LA LEY 1751",
    "ART. 30 DE LA LEY 1751",
    "ART. 44 DE LA LEY 1122",
    "ART. 20 DE LA LEY 1122",
    "ART. 23 DE LA LEY 1122",  # OK, existe pero usado en contextos inventados
    "RESOLUCIÓN 1552 DE 2019",
)


def quitar_parrafos_con_citas_inventadas(texto: str) -> str:
    """Elimina párrafos enteros que mencionen citas FRECUENTEMENTE inventadas.

    Estrategia: corta el texto por puntos seguidos de espacio (cada "oración"),
    elimina las que contengan citas conocidas como inventadas, y reconstruye.

    Es idempotente y conservador — sólo elimina oraciones que mencionan citas
    específicas que el equipo HUS confirmó NO existen en el corpus normativo
    cargado. No toca oraciones con citas válidas (Art. 87 Decreto 2423, etc.).
    """
    if not texto or not isinstance(texto, str):
        return texto

    texto_upper = texto.upper()
    # Optimización: si no hay ninguna cita inventada conocida, no hacemos nada
    if not any(c in texto_upper for c in _CITAS_INVENTADAS_FRECUENTES):
        return texto

    # Split por oraciones (puntos + espacio). Mantiene puntos finales.
    oraciones = re.split(r"(?<=\.)\s+", texto)
    oraciones_limpias: list[str] = []
    eliminadas = 0
    for o in oraciones:
        o_upper = o.upper()
        if any(c in o_upper for c in _CITAS_INVENTADAS_FRECUENTES):
            eliminadas += 1
            continue
        oraciones_limpias.append(o)

    if eliminadas == 0:
        return texto

    resultado = " ".join(oraciones_limpias).strip()
    # Si quedó texto vacío o muy corto (eliminamos demasiado), devolver original
    if len(resultado) < len(texto) * 0.4:
        return texto
    return resultado
