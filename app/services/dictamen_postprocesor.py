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
    # 22 mayo 2026 — citas que la IA sigue inventando (dictamen TA0201 PPL):
    "ART. 2 DE LA LEY 1438",
    "ART. 2 LEY 1438",
    "ARTÍCULO 2 DE LA LEY 1438",
    "ART. 1 DE LA LEY 1751",
    "ART. 1 LEY 1751",
    "ARTÍCULO 1 DE LA LEY 1751",
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


def _extraer_componentes_cita(cita: str) -> tuple[str, str, str]:
    """Extrae (numero_articulo, numero_norma, año) de una cita.

    Ejemplos:
      'Art. 2 LEY 1438/2011' → ('2', '1438', '2011')
      'Art. 10 DECRETO 780/2016' → ('10', '780', '2016')
      'Resolución 1552/2019' → ('', '1552', '2019')
    """
    c = cita.upper()
    m_art = re.search(r"ART\.?\s*(\d+)", c)
    m_norma = re.search(r"(?:LEY|DECRETO|RESOLUCI[ÓO]N)\s+(\d+)\s*[/\s]\s*(\d{4})", c)
    art = m_art.group(1) if m_art else ""
    num = m_norma.group(1) if m_norma else ""
    anio = m_norma.group(2) if m_norma else ""
    return (art, num, anio)


def quitar_citas_invalidas_dinamico(texto: str, eps: str | None = None) -> str:
    """Versión MÁS PODEROSA del postprocessor: usa el verificador oficial
    del HUS (citation_verifier.verificar_citas) para detectar DINÁMICAMENTE
    las citas inválidas y eliminar los párrafos que las contienen.

    Matching inteligente: compara por componentes (núm artículo + núm ley
    + año), tolerando variantes como "Art. 2 LEY 1438/2011" vs
    "ARTÍCULO 2 DE LA LEY 1438 DE 2011".

    Filosofía: si el validador del HUS marca como ARTICULO_FUERA_DE_NORMA
    una cita, debemos quitarla del dictamen antes de mostrarlo.

    Returns:
        texto con las oraciones que contienen citas inválidas eliminadas.
        Si eliminar dejaría texto < 40% del original, devuelve el original.
    """
    if not texto or not isinstance(texto, str):
        return texto

    try:
        from app.services.citation_verifier import verificar_citas
    except ImportError:
        return texto

    try:
        reporte = verificar_citas(texto, eps=eps)
    except Exception:
        return texto

    issues = reporte.get("issues", [])
    if not issues:
        return texto

    # Extraer componentes (art, num_norma, año) de cada cita problemática
    componentes_invalidos: list[tuple[str, str, str]] = []
    for i in issues:
        if i.get("severidad") in ("ALTA", "MEDIA") and i.get("cita"):
            comps = _extraer_componentes_cita(i["cita"])
            # Solo agregar si tiene al menos núm norma + año (para evitar false positives)
            if comps[1] and comps[2]:
                componentes_invalidos.append(comps)

    if not componentes_invalidos:
        return texto

    def oracion_tiene_cita_invalida(oracion: str) -> bool:
        o_upper = oracion.upper()
        for art, num, anio in componentes_invalidos:
            # La oración debe contener TODOS los componentes para considerarse match
            if art and f" {art} " not in f" {o_upper} ":
                continue
            if num not in o_upper:
                continue
            if anio not in o_upper:
                continue
            # Verificar que cerca del núm haya palabra LEY/DECRETO/RESOLUCIÓN
            patron = rf"(?:LEY|DECRETO|RESOLUCI[ÓO]N)\s+{re.escape(num)}.*?{anio}"
            if re.search(patron, o_upper):
                return True
        return False

    # Split por oraciones, eliminar las que mencionan alguna cita problemática
    oraciones = re.split(r"(?<=\.)\s+", texto)
    oraciones_limpias: list[str] = []
    eliminadas = 0
    for o in oraciones:
        if oracion_tiene_cita_invalida(o):
            eliminadas += 1
            continue
        oraciones_limpias.append(o)

    if eliminadas == 0:
        return texto

    resultado = " ".join(oraciones_limpias).strip()
    # Safety: no eliminar más del 60% del texto
    if len(resultado) < len(texto) * 0.4:
        return texto
    return resultado
