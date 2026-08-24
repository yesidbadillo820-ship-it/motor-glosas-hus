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

# Ronda 21 (caso MEDIMÁS): marcadores de CODA PROCESAL que la IA encadena
# tras el cierre con una CONJUNCIÓN (sin punto), por lo que el truncado por
# "primer punto" no los recortaba ("...de la glosa Y, de persistir
# Punto que de verdad cierra una oración. NO el separador de miles de
# «$ 12.300.000», NO el de una sigla pegada («E.S.E.») y NO el de una
# abreviatura seguida de número («ART. 87», «NO. 12345»). Los cuatro casos
# salieron cortados en dictámenes reales.
# El lookbehind cubre el punto FINAL de una sigla («E.S.E. HOSPITAL»): por
# su forma es idéntico a un fin de oración, y solo se distingue por venir
# detrás de otra letra abreviada.
_RE_FIN_ORACION = re.compile(r"(?<!\.\w)\.(?!\w)(?!\s*\d)", re.UNICODE)

# discrepancias, se invita a mesa de conciliación..."). Si un marcador
# aparece ANTES del primer punto de la cola, se corta en el ancla.
_MARCADORES_CODA = re.compile(
    r"SE\s+INVITA|MESA\s+DE\s+CONCILIACI|DE\s+PERSISTIR|"
    r"10\s+D[ÍI]AS|ART\.?\s*57|QUEDAMOS\s+ATENTOS|ESCALERA\s+PROCESAL",
    re.IGNORECASE,
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
    # El punto que cierra la oración, no cualquier punto. Buscar el primero
    # a secas cortaba dentro de los separadores de miles: el 05-08-2026 un
    # dictamen salió terminando en «…EL RECONOCIMIENTO ÍNTEGRO DEL VALOR
    # $ 12.» — el punto de «12.300.000». No era el modelo truncando, era
    # este corte. Con el mismo regex se arreglan tres hermanos del mismo
    # defecto: «…A LA E.» (de E.S.E.), «…CONFORME AL ART.» (ART. 87) y
    # «…FACTURA NO.» (NO. 12345).
    _mp = _RE_FIN_ORACION.search(cola)
    rel = _mp.start() if _mp else -1
    # Ronda 21: si una coda procesal arranca ANTES del primer punto (típico
    # cuando se une por conjunción: "...de la glosa Y, de persistir..."),
    # cortar en el ancla. La continuación legítima ("Y EL RECONOCIMIENTO
    # ÍNTEGRO...") no trae estos marcadores y se preserva.
    mc = _MARCADORES_CODA.search(cola)
    if mc and (rel == -1 or mc.start() < rel):
        return texto[: m.end()].rstrip().rstrip(",") + "."
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
    # OJO ANTES DE "ARREGLAR" ESTA EXPRESION (24-08-2026). Reconoce
    # "RESOLUCION 1552/2019" pero NO "Resolución 1552 de 2019", que es
    # justamente el formato con que el verificador escribe las citas de
    # NORMA_INEXISTENTE. O sea que una norma inventada nunca llego a esta
    # lista y nunca se borro por este camino.
    #
    # Se deja asi A PROPOSITO. Ampliarla para que acepte " de " haria que se
    # borren oraciones enteras por cada norma que no este en el corpus, y el
    # corpus tiene 131 normas de las miles que existen: una resolucion real
    # que no hayamos cargado saldria del documento radicado sin que nadie se
    # entere. Ese es exactamente el dano que se acaba de corregir con los
    # articulos (ver el aviso ARTICULO_NO_VERIFICABLE en citation_verifier).
    #
    # El aviso igual le llega al gestor: sale en rojo en el panel de
    # verificacion de citas, que es donde debe decidirlo una persona.
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
        # ATRIBUCION_FALSA no se trata aquí (24-08-2026). Los demás hallazgos
        # con forma de norma dicen «esta cita no existe», y borrar la frase
        # entera es lo correcto. Ese dice algo distinto: el artículo SÍ existe,
        # lo que está mal es el contenido que se le atribuyó. Si se borrara por
        # componentes, se llevaría por delante también las frases donde ese
        # mismo artículo está bien citado en el mismo dictamen. El hallazgo se
        # le muestra al auditor y hace que el Quality Gate mande a rehacer.
        if i.get("tipo") == "ATRIBUCION_FALSA":
            continue
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
