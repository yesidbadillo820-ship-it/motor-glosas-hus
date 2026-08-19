"""
citation_verifier.py — Valida que las normas y citas legales en el dictamen
correspondan al texto real del corpus normativa_completa.

Detecta 4 problemas comunes que la EPS usa para ratificar glosas:
  1. NORMA_INEXISTENTE — dictamen cita "Res. 9999/2099" que no existe
  2. ARTICULO_FUERA_DE_NORMA — cita Art. 47 de norma que no tiene Art. 47
  3. CITA_LITERAL_FALSA — texto entrecomillado «...» que no aparece literal
  4. CITA_VACIA — comillas atribuidas a una norma pero sin texto adentro
     («.»), que hasta el 18-08-2026 salían selladas como «cita verificada»

Salida: lista de issues con severidad. La UI los muestra como warnings
debajo del dictamen y sugiere reformulación.

NO bloquea el envío — el gestor decide si corrige o ignora. Pero al menos
no manda el dictamen a ciegas con citas inventadas.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("motor_glosas")


# Patrones de citación legal típicos en dictámenes ESE HUS
# Todos los patrones exigen \b al inicio: sin él, la alternativa "Res..."
# matcheaba la cola de palabras ("...TRES 500/2024") y la (T|C|SU) de
# sentencias se disparaba con la C final de "DEC. 4747/2007" — visto en
# producción 10-jun-2026: el dictamen citaba "MESA DE CONCILIACIÓN DE
# AUDITORÍA (ART. 20 DEC. 4747/2007)" y el verifier reportaba la sentencia
# fantasma "C-4747/2007" como NORMA_INEXISTENTE.
# 06-08-2026 — la palabra iba con tilde obligatoria y es la ÚNICA de las
# cinco que la lleva. El dictamen se radica en MAYÚSCULA SOSTENIDA y hay
# rutas que pierden la tilde: escrito "RESOLUCION 9999 DE 2030", el
# verificador ni siquiera lo contaba como cita, así que una resolución
# inventada salía con el sello «citas verificadas · 0 hallazgos».
PAT_RESOLUCION = re.compile(
    r"\bResoluci[óo]n\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})"
    r"|\bRes(?:oluci[óo]n)?\.?\s*(\d{1,5})\s*(?:[/\-]|\s+de\s+)\s*(\d{2,4})\b",
    re.IGNORECASE,
)
# La 2.ª alternativa acepta la abreviatura "Dec. 4747/2007" (antes solo
# "Decreto NNN/YYYY" — la forma abreviada ni se contaba como cita).
PAT_DECRETO = re.compile(
    r"\bDecreto\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})|\bDec(?:reto)?\.?\s*(\d{1,5})\s*(?:[/\-]|\s+de\s+)\s*(\d{2,4})\b",
    re.IGNORECASE,
)
# El lookbehind excluye "DECRETO-LEY 1795 DE 2000" / "DECRETO LEY ...":
# son DECRETOS con fuerza de ley, no leyes — el 11-jun-2026 el verifier
# extraía "Ley 1795 de 2000" del texto fijo DMBUG y la marcaba
# NORMA_INEXISTENTE ALTA (la norma real es el Decreto-Ley 1795/2000).
PAT_LEY = re.compile(
    # Ronda 7 (16-jun-2026 — fix R): los lookbehinds solo cubrían ASCII "-"
    # y espacio normal. Evidencia caso 9 FOMAG: el dictamen escribió
    # "Decreto‑Ley 1295/1994" con guión Unicode U+2011 (non-breaking
    # hyphen), saltando ambos lookbehinds, y el verifier marcaba
    # "Ley 1295/1994" como NORMA_INEXISTENTE ALTA. Ampliamos a todos los
    # guiones Unicode (U+002D, U+2010-U+2015) y espacios (regular, NBSP).
    r"(?<![Dd][Ee][Cc][Rr][Ee][Tt][Oo][\-‐‑‒–—―])"
    r"(?<![Dd][Ee][Cc][Rr][Ee][Tt][Oo][\s ])"
    r"\bLey\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})"
    r"|(?<![Dd][Ee][Cc][Rr][Ee][Tt][Oo][\-‐‑‒–—―])"
    r"(?<![Dd][Ee][Cc][Rr][Ee][Tt][Oo][\s ])"
    r"\bLey\s+(\d{1,5})[/\-](\d{2,4})",
    re.IGNORECASE,
)
PAT_ACUERDO = re.compile(
    r"\bAcuerdo\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})|\bAcuerdo\s+(\d{1,5})[/\-](\d{2,4})",
    re.IGNORECASE,
)
PAT_CIRCULAR = re.compile(
    r"\bCircular\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})|\bCircular\s+(\d{1,5})[/\-](\d{2,4})",
    re.IGNORECASE,
)
# 06-08-2026 — solo se reconocía la forma con barra o guion ("T-760/2008").
# La forma que escribe el motor en prosa —"Sentencia T-994 de 2029"— no se
# contaba como cita, así que una sentencia inventada pasaba sin revisar. Es
# la trampa que Yesid puso en la glosa CL0301 de FAMISANAR.
PAT_SENTENCIA = re.compile(
    r"(?:Sentencia\s+)?\b(T|C|SU)[\.\-]?\s*(\d{1,4})\s*(?:[/\-]|\s+de\s+)\s*(\d{2,4})\b",
    re.IGNORECASE,
)
PAT_ARTICULO = re.compile(
    r"(?:art(?:ículo|iculo|\.)\s*)(\d{1,4})(?:\s*(?:de\s+(?:la\s+)?(Resolución|Ley|Decreto)\s+(?:N[oº°\.]?\s*)?(\d{1,5})\s+de\s+(\d{4})))?",
    re.IGNORECASE,
)
# Texto entrecomillado — chevrones franceses « » preferidos en el motor
PAT_CITA_LITERAL = re.compile(r"«([^«»]{15,800})»")
# 18-08-2026 — LA COMILLA VACÍA NO LA VEÍA NADIE.
# El patrón de arriba exige 15 caracteres adentro. «.» tiene uno, así que ni
# siquiera se contaba como cita: pasaba invisible por las cuatro revisiones.
# Caso real de ese día (NUEVA EPS, glosa de tarifa de $12.000): el dictamen
# salió con «EN VIRTUD DE ART. 168 LA LEY 100 DE 1993, QUE DISPONE «.»» y con
# el sello «7 citas verificadas · 0 hallazgos» debajo. La IA abrió comillas
# para citar el artículo y no escribió nada.
# Los chevrones en este repositorio solo se usan para citar, así que cualquiera
# vacío es sospechoso. Con comillas rectas o curvas se exige además el verbo
# normativo delante, para no confundirse con una comilla suelta del texto.
PAT_CITA_VACIA_CHEVRON = re.compile(r"«([^«»]{0,14})»")
PAT_CITA_VACIA_ATRIBUIDA = re.compile(
    r"(?:ESTABLECE|DISPONE|SEÑALA|SENALA|CONSAGRA|REZA|INDICA|PRECEPT[ÚU]A|"
    r"RECUERDA|PREV[ÉE]|CONTEMPLA|ORDENA|DETERMINA|ESTIPULA|PACTA|REAFIRMA|"
    r"PRESCRIBE)"
    r"\s*(?:QUE\s*)?(?:TEXTUALMENTE\s*)?:?\s*"
    r"[\"“‘']([^\"“”‘’']{0,14})[\"”’']",
    re.IGNORECASE,
)
# Citas "textuales" con comillas dobles/simples ATRIBUIDAS a una norma o
# cláusula (ESTABLECE/DISPONE/SEÑALA/...). Auditoría 10-jun-2026 P0-1:
# la red solo cubría chevrones, así que "CLÁUSULA 12 DEL CONTRATO QUE
# ESTABLECE: 'LAS PARTES SE OBLIGAN A NO REBATIR...'" (fabricada y
# autodestructiva) y los arts. 44/45/46 L1438 con texto inventado entre
# comillas dobles se radicaban sin una sola alarma. Se exige el verbo
# de atribución para no flaggear citas del texto de la glosa misma
# ("LA AFIRMACIÓN DE QUE '...'" no es una cita normativa).
PAT_CITA_ATRIBUIDA = re.compile(
    r"(?:ESTABLECE|DISPONE|SEÑALA|SENALA|CONSAGRA|REZA|INDICA|PRECEPT[ÚU]A|"
    # 06-08-2026: faltaban los verbos con que el motor introduce una cita
    # cuando no la atribuye a una norma concreta. Ver PAT_CITA_AUTOATRIBUIDA.
    r"RECUERDA|PREV[ÉE]|CONTEMPLA|ORDENA|DETERMINA|ESTIPULA|PACTA)"
    r"\s*(?:QUE\s*)?(?:TEXTUALMENTE\s*)?:?\s*"
    r"[\"“‘']([^\"“”‘’']{15,800})[\"”’']",
    re.IGNORECASE,
)
# Cita que se atribuye a sí misma: el sujeto normativo va DENTRO de las
# comillas, así que no hay verbo de atribución delante y las dos redes
# anteriores no la veían.
#
# Prueba real del 06-08-2026, glosa de sanción de COOSALUD:
#
#   SE RECUERDA QUE “EL CONTRATO ESTABLECE QUE LAS SANCIONES POR
#   INCUMPLIMIENTO SOLO PODRÁN APLICARSE CUANDO EXISTAN DISPOSICIONES
#   CONTRACTUALES ESPECÍFICAS”.
#
# Nadie había cargado ese contrato. El dictamen se entregó con el sello
# «7 citas contra corpus · 0 hallazgos», que es peor que no revisar: le dice
# al auditor que está verificado.
#
# Se exige que la cita ARRANQUE con el sujeto normativo y tenga cuerpo
# (≥40 chars). Una cita del texto de la glosa ("no se evidencia epicrisis")
# no empieza así y no se toca.
PAT_CITA_AUTOATRIBUIDA = re.compile(
    r"[\"“«‘']\s*("
    r"(?:EL|LA|LOS|LAS)\s+"
    r"(?:CONTRATO|CL[ÁA]USULA|LEY|RESOLUCI[ÓO]N|DECRETO|ART[ÍI]CULO|"
    r"CIRCULAR|ACUERDO|MANUAL|ANEXO|SENTENCIA)\b"
    r"[^\"“”«»‘’']{40,800})"
    r"[\"”»’']",
    re.IGNORECASE,
)
# Limpia HTML para comparar texto plano
PAT_HTML = re.compile(r"<[^>]+>")


def _quitar_html(s: str) -> str:
    return re.sub(r"\s+", " ", PAT_HTML.sub(" ", s or "")).strip()


def _normalizar(s: str) -> str:
    """Lower + sin acentos + sin puntuación + sin espacios extras para
    comparar fragmentos sin sufrir por mayúsculas/tildes/comillas."""
    if not s:
        return ""
    repl = str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")
    s = s.translate(repl).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_PREFIJO_UPPER = {
    # forma corta usada por verificar_citas (tipo_label[:3].lower())
    "ley": "LEY",
    "dec": "DECRETO",
    "res": "RESOLUCION",
    "acu": "ACUERDO",
    "cir": "CIRCULAR",
    # forma larga, por si algún caller futuro pasa el tipo completo
    "decreto": "DECRETO",
    "resolucion": "RESOLUCION",
    "acuerdo": "ACUERDO",
    "circular": "CIRCULAR",
}


def _buscar_clave_norma(tipo: str, numero: str, anio: str, normas: dict) -> Optional[str]:
    """Mapea (tipo, número, año) a la clave en _TODAS_LAS_NORMAS.

    El corpus actual usa MAYORITARIAMENTE el formato upper-words:
      "LEY 100 DE 1993", "LEY 1438 DE 2011", "DECRETO 4747 DE 2007",
      "ACUERDO 002 DE 2001 CSSFFMM", "CIRCULAR 025 DE 2024".
    También intentamos snake_case ("ley_1438_2011") por compatibilidad.

    El fallback antiguo matcheaba por sustring numérico → "138" caía dentro
    de "LEY 1438 DE 2011" como falso positivo. Ahora se exige que el número
    aparezca como token entre espacios o como segmento entre guiones bajos.
    """
    n = numero.lstrip("0") or numero
    tipo_l = tipo.lower()
    prefijo_up = _PREFIJO_UPPER.get(tipo_l)

    candidatos: list[str] = [
        # snake_case (formato histórico)
        f"{tipo_l}_{n}_{anio}",
        f"{tipo_l}_{numero}_{anio}",
    ]
    if prefijo_up:
        # upper-words (formato actual del corpus)
        numero_padded = numero.zfill(3) if len(numero) < 3 else numero
        candidatos.extend(
            [
                f"{prefijo_up} {n} DE {anio}",
                f"{prefijo_up} {numero} DE {anio}",
                f"{prefijo_up} {numero_padded} DE {anio}",
            ]
        )
    if tipo_l in ("t", "c", "su"):
        candidatos.append(f"sentencia_{n.lower()}_{anio}")
        # Ronda 19 (Bug CC, 30-jun-2026): el corpus actual usa el formato
        # upper-words "SENTENCIA T-121 DE 2015", "SENTENCIA SU-1023 DE 2001".
        # Antes solo se generaba snake_case → T-121/2015 (que SÍ está en el
        # corpus) se marcaba NORMA_INEXISTENTE y bajaba la confianza del
        # dictamen. Generamos también el formato upper-words del corpus.
        sala_up = tipo_l.upper()
        candidatos.extend(
            [
                f"SENTENCIA {sala_up}-{n} DE {anio}",
                f"SENTENCIA {sala_up}-{numero} DE {anio}",
                f"SENTENCIA {sala_up}{n} DE {anio}",
            ]
        )

    for c in candidatos:
        if c and c in normas:
            return c

    # Ronda 19 (Bug CC): coincidencia tolerante para sentencias. Cubre
    # variantes en la clave del corpus (con/sin guión entre sala y número).
    if tipo_l in ("t", "c", "su"):
        sala_up = tipo_l.upper()
        for k in normas.keys():
            if not k.startswith(f"SENTENCIA {sala_up}"):
                continue
            if f" DE {anio}" not in k:
                continue
            # Extraer el número entre "SENTENCIA {SALA}" y " DE "
            resto = k[len(f"SENTENCIA {sala_up}") :].lstrip("-").strip()
            cand_num = resto.split(" DE ")[0].strip().lstrip("0") or "0"
            if cand_num == n:
                return k

    # Coincidencia tolerante: clave que empieza por el prefijo, contiene
    # el número como token entre espacios, y termina/contiene " DE YYYY".
    # Resuelve casos con sufijo en la clave (p.ej. "ACUERDO 002 DE 2001 CSSFFMM").
    if prefijo_up:
        for k in normas.keys():
            if not k.startswith(f"{prefijo_up} "):
                continue
            if f" DE {anio}" not in k:
                continue
            # Extraer el número entre el prefijo y "DE"
            resto = k[len(prefijo_up) + 1 :]
            cand_num = resto.split(" DE ")[0].strip().lstrip("0") or "0"
            if cand_num == n:
                return k

    # Fallback final estricto en snake_case
    token_n = f"_{n}_"
    token_anio_end = f"_{anio}"
    for k in normas.keys():
        if token_n in k and k.endswith(token_anio_end):
            return k
    return None


def _corpus_clausulas_contrato(eps: Optional[str] = None) -> str:
    """Construye un corpus normalizado con el texto literal de las
    clausulas extraidas del PDF del contrato firmado.

    Si se pasa `eps`, filtra solo las clausulas de esa EPS; si no, incluye
    TODAS las clausulas de TODOS los contratos. Lo segundo es mas permisivo
    (una cita del contrato de Compensar podria pasar como valida en una
    glosa de Sanitas) pero evita falsos positivos cuando el call site no
    conoce la EPS.

    Retorna string normalizado vacio si no hay clausulas o si la BD falla.
    """
    try:
        from app.database import SessionLocal
        from app.models.db import ClausulaContrato

        db = SessionLocal()
        try:
            q = db.query(ClausulaContrato)
            if eps:
                q = q.filter(ClausulaContrato.eps == eps.upper())
            textos = [(cl.texto_literal or "") for cl in q.all()]
            return " ".join(_normalizar(t) for t in textos if t)
        finally:
            db.close()
    except Exception:
        return ""


# «CUPS 348240», «código CUPS: 871121», «CUPS890201». Se piden 6 dígitos, que
# es como son los CUPS del Ministerio; con menos se confundiría con valores.
PAT_CUPS = re.compile(r"\bCUPS\s*:?\s*(\d{6})\b", re.IGNORECASE)


def _verificar_cups(texto: str, issues: list[dict]) -> None:
    """Marca los CUPS que el dictamen cita y no existen en el catálogo.

    Caso real 19-08-2026, factura HUS468334: el dictamen decía «Servicio
    objetado: RADIOGRAFÍA DE RODILLA CUPS 348240» y ese código NO EXISTE. El
    verificador revisaba resoluciones, decretos, leyes y sentencias — pero
    ningún CUPS —, así que el documento salía sellado con «11 citas contra
    corpus · 0 hallazgos» llevando un código inventado.

    Un CUPS es de lo primero que la EPS cruza contra su sistema. Uno inventado
    en un documento radicado tumba la defensa entera, aunque el argumento
    jurídico sea correcto.
    """
    try:
        from app.services.cups_soat_service import buscar_cups, descripcion_cups
    except Exception:  # pragma: no cover - sin catálogo no se inventa un fallo
        return

    revisados: set[str] = set()
    for cups in PAT_CUPS.findall(texto or ""):
        if cups in revisados:
            continue
        revisados.add(cups)
        try:
            existe = bool(descripcion_cups(cups)) or bool(buscar_cups(cups, limite=1))
        except Exception:  # pragma: no cover
            continue
        if existe:
            continue
        issues.append(
            {
                "tipo": "CUPS_INEXISTENTE",
                "severidad": "ALTA",
                "cita": f"CUPS {cups}",
                "detalle": (
                    f"El código CUPS {cups} no existe en el catálogo oficial. La EPS "
                    "cruza los CUPS contra su sistema: un código inventado tumba la "
                    "defensa completa, así el argumento jurídico esté bien."
                ),
                "sugerencia": (
                    "Busque el CUPS real del servicio en «Consulta Normativa» y "
                    "corríjalo, o quite la mención del código y deje solo el nombre "
                    "del procedimiento."
                ),
            }
        )


def verificar_citas(dictamen_html: str, eps: Optional[str] = None) -> dict:
    """Escanea el dictamen y devuelve un reporte de validación.

    Estructura:
        {
          "total_citas": int,
          "ok": int,
          "issues": [
            {
              "tipo": "NORMA_INEXISTENTE" | "ARTICULO_FUERA_DE_NORMA"
                      | "CITA_LITERAL_FALSA" | "CITA_VACIA",
              "severidad": "ALTA" | "MEDIA" | "BAJA",
              "cita": str,      # lo que aparece en el dictamen
              "detalle": str,   # explicación
              "sugerencia": str | None,
            }
          ],
          "tiene_problemas_graves": bool,  # alguna severidad ALTA
        }

    Si el corpus no se puede importar, devuelve reporte vacío (no rompe nada).
    """
    issues: list[dict] = []
    total_citas = 0

    # 19-08-2026. Estos dos caminos devolvían lo MISMO que «revisé y está
    # limpio»: cero citas, cero problemas. Y con eso el dictamen se llevaba el
    # sello verde «✓ VALIDADO POR QUALITY GATE» sin que nadie lo hubiera
    # revisado — un sello de calidad sobre un documento que se radica ante la
    # EPS, puesto sin haber mirado nada.
    #
    # `verificado` distingue las dos cosas. La pantalla solo estampa el sello
    # cuando es True.
    try:
        from app.services.normativa_completa import _TODAS_LAS_NORMAS as normas
    except Exception as e:  # noqa: BLE001 - se avisa, no se finge
        logger.warning("[CITAS] no se pudo cargar el corpus de normas: %s", e)
        return {
            "total_citas": 0,
            "ok": 0,
            "issues": [],
            "tiene_problemas_graves": False,
            "verificado": False,
            "motivo_no_verificado": (
                "No se pudo cargar el corpus de normas del sistema, así que las "
                "citas de este dictamen NO se revisaron. Verifíquelas a mano "
                "antes de radicar."
            ),
        }

    if not dictamen_html:
        return {
            "total_citas": 0,
            "ok": 0,
            "issues": [],
            "tiene_problemas_graves": False,
            "verificado": False,
            "motivo_no_verificado": "El dictamen llegó vacío: no había qué revisar.",
        }

    texto = _quitar_html(dictamen_html)

    # 1. Verificar Resoluciones / Decretos / Leyes / Acuerdos / Circulares
    for pat, tipo_label in (
        (PAT_RESOLUCION, "Resolución"),
        (PAT_DECRETO, "Decreto"),
        (PAT_LEY, "Ley"),
        (PAT_ACUERDO, "Acuerdo"),
        (PAT_CIRCULAR, "Circular"),
    ):
        for m in pat.finditer(texto):
            total_citas += 1
            grupos = [g for g in m.groups() if g]
            if len(grupos) >= 2:
                numero, anio = grupos[0], grupos[1]
                if len(anio) == 2:
                    anio = "20" + anio if int(anio) < 50 else "19" + anio
                tipo_short = tipo_label[:3].lower()
                clave = _buscar_clave_norma(tipo_short, numero, anio, normas)
                if not clave:
                    issues.append(
                        {
                            "tipo": "NORMA_INEXISTENTE",
                            "severidad": "ALTA",
                            "cita": f"{tipo_label} {numero} de {anio}",
                            "detalle": f"No existe en el corpus normativo cargado ({tipo_label} {numero}/{anio}).",
                            "sugerencia": "Verifica la cita o reemplaza por una norma vigente del corpus.",
                        }
                    )

    # 2. Verificar Sentencias
    for m in PAT_SENTENCIA.finditer(texto):
        total_citas += 1
        sala, num, anio = m.groups()
        if len(anio) == 2:
            anio = "20" + anio if int(anio) < 50 else "19" + anio
        clave = _buscar_clave_norma(sala.lower(), num, anio, normas)
        if not clave:
            issues.append(
                {
                    "tipo": "NORMA_INEXISTENTE",
                    "severidad": "MEDIA",
                    "cita": f"Sentencia {sala.upper()}-{num}/{anio}",
                    "detalle": "Sentencia no incluida en el corpus jurisprudencial.",
                    "sugerencia": "Verifica que la sentencia exista o reemplaza por una conocida (ej: T-760/2008, T-1025/2002).",
                }
            )

    # 3. Verificar artículos cuando se citan junto a su norma
    for m in PAT_ARTICULO.finditer(texto):
        art_num = m.group(1)
        norma_tipo = m.group(2)
        norma_num = m.group(3)
        norma_anio = m.group(4)
        if not (norma_tipo and norma_num and norma_anio):
            continue
        total_citas += 1
        clave = _buscar_clave_norma(norma_tipo[:3].lower(), norma_num, norma_anio, normas)
        if clave:
            n = normas[clave]
            arts = n.get("articulos", {}) or {}
            # Las claves de articulos pueden ser strings o ints
            keys_art = {str(k) for k in arts.keys()}
            if str(art_num) not in keys_art:
                issues.append(
                    {
                        "tipo": "ARTICULO_FUERA_DE_NORMA",
                        "severidad": "MEDIA",
                        "cita": f"Art. {art_num} {norma_tipo} {norma_num}/{norma_anio}",
                        "detalle": f"La {norma_tipo} {norma_num}/{norma_anio} no contiene el Art. {art_num} en el corpus cargado.",
                        "sugerencia": "Verifica el número de artículo o consulta los artículos disponibles de esta norma.",
                    }
                )

    # 4. Citas VACÍAS: comillas abiertas para citar la norma, sin texto adentro.
    # Van antes de las citas literales porque no hay nada que contrastar contra
    # el corpus: el defecto es que la cita no dice nada.
    vacias_vistas: set[str] = set()
    for pat_vacia in (PAT_CITA_VACIA_CHEVRON, PAT_CITA_VACIA_ATRIBUIDA):
        for cruda in pat_vacia.findall(texto):
            if any(c.isalnum() for c in cruda):
                continue  # tiene contenido: no es una cita vacía
            clave = cruda.strip()
            if clave in vacias_vistas:
                continue
            vacias_vistas.add(clave)
            total_citas += 1
            issues.append(
                {
                    "tipo": "CITA_VACIA",
                    "severidad": "ALTA",
                    "cita": "«" + clave + "»",
                    "detalle": (
                        "El dictamen abre comillas para citar la norma y no escribe el "
                        "texto: la cita queda vacía. Radicado así, la entidad puede "
                        "alegar que el prestador no sustentó su defensa."
                    ),
                    "sugerencia": (
                        "Escribe el texto literal del artículo citado, o quita las "
                        "comillas y deja solo la referencia a la norma."
                    ),
                }
            )

    # 5. Verificar citas literales: entre chevrones «» Y entre comillas
    # dobles/simples cuando van atribuidas a una norma o cláusula
    # (ESTABLECE/DISPONE/...). Ambas se contrastan contra el mismo
    # corpus (normas + cláusulas reales del contrato en BD).
    citas_literales = PAT_CITA_LITERAL.findall(texto)
    citas_literales += PAT_CITA_ATRIBUIDA.findall(texto)
    citas_literales += [
        c for c in PAT_CITA_AUTOATRIBUIDA.findall(texto) if c not in citas_literales
    ]
    if citas_literales:
        # Construir corpus completo de TODOS los textos normativos para búsqueda
        corpus_normas = " ".join(
            _normalizar(n.get("texto", ""))
            + " "
            + _normalizar(n.get("ratio_literal", ""))
            + " "
            + _normalizar(n.get("extracto_judicial", ""))
            + " "
            + " ".join(_normalizar(a.get("texto", "")) for a in (n.get("articulos") or {}).values())
            for n in normas.values()
        )
        # Ampliar corpus con clausulas literales extraidas del PDF del contrato
        # firmado con la EPS. Una cita textual del contrato debe pasar como
        # VALIDA (no como CITA_LITERAL_FALSA) — el contrato es texto autoritativo
        # tan valido como una norma.
        corpus_clausulas = _corpus_clausulas_contrato(eps=eps)
        corpus_normalizado = corpus_normas + " " + corpus_clausulas
        for cita in citas_literales:
            total_citas += 1
            cita_norm = _normalizar(cita)
            # ── Cita VACÍA ────────────────────────────────────────────────
            # Caso real 18-08-2026 (NUEVA EPS, glosa de tarifa $12.000): el
            # dictamen decía «EN VIRTUD DE ART. 168 LA LEY 100 DE 1993, QUE
            # DISPONE «.»». La IA abrió comillas para citar el artículo y
            # escribió un punto. El corte de abajo —"menos de 30 caracteres
            # no se alcanza a verificar"— la dejaba pasar SIN revisar y
            # además la contaba como cita buena: el dictamen salía sellado
            # con «7 citas verificadas · 0 hallazgos». Una comilla sin texto
            # atribuida a una norma no es una cita corta: es una cita que no
            # dice nada, y en un documento radicado le entrega a la EPS el
            # argumento de que el prestador no sustentó su defensa.
            contenido = "".join(c for c in cita_norm if c.isalnum())
            if len(contenido) < 3:
                issues.append(
                    {
                        "tipo": "CITA_VACIA",
                        "severidad": "ALTA",
                        "cita": "«" + cita.strip() + "»",
                        "detalle": (
                            "El dictamen abre comillas para citar la norma y no escribe "
                            "el texto: la cita queda vacía. Así radicado, la entidad puede "
                            "alegar que la defensa no fue sustentada."
                        ),
                        "sugerencia": (
                            "Escribe el texto literal del artículo citado, o quita las "
                            "comillas y deja solo la referencia a la norma."
                        ),
                    }
                )
                continue
            # Tomamos un fragmento mid de 30 chars como "huella" para buscar
            if len(cita_norm) < 30:
                continue
            mid = cita_norm[10 : min(len(cita_norm) - 10, 80)]
            if mid and mid not in corpus_normalizado:
                # Probamos también con los primeros 60 chars
                inicio = cita_norm[:60]
                if inicio not in corpus_normalizado:
                    issues.append(
                        {
                            "tipo": "CITA_LITERAL_FALSA",
                            "severidad": "ALTA",
                            "cita": "«" + (cita[:140] + "..." if len(cita) > 140 else cita) + "»",
                            "detalle": (
                                "Este texto entrecomillado no se encuentra literalmente en el "
                                "corpus normativo ni en las cláusulas reales del contrato cargadas. "
                                "Puede ser una cita inventada por la IA."
                            ),
                            "sugerencia": (
                                "Reemplaza el texto entre comillas por una cita literal de una "
                                "norma o cláusula real, o quita las comillas si solo querías parafrasear."
                            ),
                        }
                    )

    # 6. Códigos CUPS que no existen en el catálogo oficial.
    _verificar_cups(texto, issues)
    total_citas += len(PAT_CUPS.findall(texto))

    ok = max(0, total_citas - len(issues))
    tiene_graves = any(i["severidad"] == "ALTA" for i in issues)

    if issues:
        logger.info(
            f"[CITATION-VERIFIER] {len(issues)} issues "
            f"({sum(1 for i in issues if i['severidad'] == 'ALTA')} ALTA) en {total_citas} citas"
        )

    return {
        "total_citas": total_citas,
        "ok": ok,
        "issues": issues,
        "tiene_problemas_graves": tiene_graves,
        # Sí se revisó de verdad: la pantalla puede estampar el sello.
        "verificado": True,
    }
