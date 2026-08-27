"""
citation_verifier.py — Valida que las normas y citas legales en el dictamen
correspondan al texto real del corpus normativa_completa.

Detecta 6 problemas comunes que la EPS usa para ratificar glosas:
  1. NORMA_INEXISTENTE — dictamen cita "Res. 9999/2099" que no existe
  2. ARTICULO_FUERA_DE_NORMA — cita Art. 47 de norma que no tiene Art. 47
  3. CITA_LITERAL_FALSA — texto entrecomillado «...» que no aparece literal
  4. CITA_VACIA — comillas atribuidas a una norma pero sin texto adentro
     («.»), que hasta el 18-08-2026 salían selladas como «cita verificada»
  5. CUPS_INEXISTENTE — código de procedimiento que no está en el catálogo
  6. FOLIO_INVENTADO — el dictamen afirma un folio que no aparece en los
     soportes leídos (20-08-2026); requiere que el llamador pase `evidencia`

Salida: lista de issues con severidad. La UI los muestra como warnings
debajo del dictamen y sugiere reformulación.

NO bloquea el envío — el gestor decide si corrige o ignora. Pero al menos
no manda el dictamen a ciegas con citas inventadas.
"""

import re
import logging
from typing import Optional

from app.core.tz import ahora_utc

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
# «DEL DECRETO» NO SE RECONOCÍA (24-08-2026). El patrón aceptaba «de la Ley»
# y «de Ley», pero no la contracción «del», que es la forma normal de escribir
# en español: «el artículo 87 DEL Decreto 2423 de 1996». Con esa forma solo se
# capturaba el número del artículo y la norma quedaba en blanco, así que la
# cita no se revisaba contra nada. Se agregan «del», «de los», «de las», el año
# escrito con barra («Decreto 2423/1996») y dos tipos de norma que faltaban.
PAT_ARTICULO = re.compile(
    r"(?:art(?:ículo|iculo|\.)\s*)(\d{1,4})"
    r"(?:\s*(?:de\s+la|de\s+los|de\s+las|del|de)\s+"
    r"(Resoluci[óo]n|Ley|Decreto|Circular|Acuerdo)\s+(?:N[oº°\.]?\s*)?(\d{1,5})"
    r"(?:\s+de\s+|\s*[/\-]\s*)(\d{4}))?",
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
PAT_CUPS = re.compile(
    r"\bCUPS\s*:?\s*(?=[A-Za-z0-9\-]*\d)([A-Za-z0-9][A-Za-z0-9\-]{2,11})\b",
    re.IGNORECASE,
)
_PAT_ANIO_MANUAL = re.compile(r"^(?:19|20)\d{2}$")
_FORMA_INSTITUCIONAL_HUS = re.compile(r"^(?:FMQ|FMO|AGMO|S|M)\d{2,6}[A-Z]?\d{0,2}$", re.IGNORECASE)
_FORMA_CUM = re.compile(r"^\d{4,9}-\d{1,3}$")
_FORMA_CUPS = re.compile(r"^[0-9A-Z]{6}(?:[A-Z]\d{0,2}|-\d{2})?$", re.IGNORECASE)


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
        if _PAT_ANIO_MANUAL.match(cups):
            continue
        etiqueta = None
        if _FORMA_INSTITUCIONAL_HUS.match(cups):
            etiqueta = "codigo institucional del HUS"
        elif _FORMA_CUM.match(cups):
            etiqueta = "CUM (medicamento)"
        elif not _FORMA_CUPS.match(cups):
            etiqueta = "codigo de otro sistema"
        if etiqueta:
            issues.append(
                {
                    "tipo": "CODIGO_NO_ES_CUPS",
                    "severidad": "ALTA",
                    "cita": f"CUPS {cups}",
                    "detalle": (
                        f"El dictamen llama CUPS al codigo {cups}, que es un {etiqueta}. "
                        "El codigo puede ser el correcto de la factura, pero la etiqueta "
                        "no: la EPS cruza los CUPS contra su sistema, no lo encuentra y "
                        "ratifica la glosa completa."
                    ),
                    "sugerencia": (
                        f"Deje el codigo tal cual y cambie la palabra: escriba "
                        f"«{etiqueta} {cups}» en vez de «CUPS {cups}»."
                    ),
                }
            )
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


def _falta_del_corpus(tipo_label: str, numero: str, anio) -> dict:
    """Qué decir de una norma que el corpus no tiene. Son DOS casos distintos.

    27-08-2026 — El dictamen GL-135 citó la Resolución 839 de 2017 y esto la
    marcaba «NO EXISTE» en severidad ALTA. Verificada contra el normograma
    oficial de la Supersalud, esa resolución EXISTE: es conjunta de MinSalud y
    MinCultura y modifica justamente la Res. 1995 de 1999 que el mismo dictamen
    cita. El sello le estaba diciendo al auditor que una norma buena era
    inventada — el error contrario al que este revisor existe para evitar, y el
    que más rápido le quita credibilidad al sello.

    Pero no todo es igual. Hay citas que SÍ se pueden dar por falsas sin
    consultar nada, y la más clara es una norma con **fecha futura**: no puede
    existir una resolución de un año que todavía no llega. Esa sigue en ALTA.

    El resto —una norma plausible que el corpus no trae— es «no la tengo», que
    no es lo mismo que «no existe»: el corpus carga las normas de uso diario,
    no las miles que hay.
    """
    try:
        anio_num = int(str(anio)[:4])
    except (TypeError, ValueError):
        anio_num = 0
    anio_actual = ahora_utc().year  # del reloj, no escrito a mano: en enero cambiaría solo

    if anio_num > anio_actual:
        return {
            "tipo": "NORMA_INEXISTENTE",
            "severidad": "ALTA",
            "cita": f"{tipo_label} {numero} de {anio}",
            "detalle": (
                f"{tipo_label} {numero} de {anio} no puede existir: está fechada en "
                f"{anio_num} y estamos en {anio_actual}. Es una cita inventada."
            ),
            "sugerencia": "Quite la cita o reemplácela por la norma que de verdad aplica.",
        }

    return {
        "tipo": "NORMA_SIN_VERIFICAR",
        "severidad": "MEDIA",
        "cita": f"{tipo_label} {numero} de {anio}",
        "detalle": (
            f"{tipo_label} {numero} de {anio} no está cargada en el corpus del motor, "
            "así que aquí no se pudo comprobar. Esto NO quiere decir que no exista: "
            "el corpus solo trae las normas de uso diario. Confírmela usted antes de "
            "radicar."
        ),
        "sugerencia": (
            "Búsquela en el normograma de la Supersalud o en la página del Ministerio. "
            "Si es correcta y se va a usar seguido, pídame cargarla al corpus para que "
            "quede verificada de aquí en adelante."
        ),
    }


def _estado_del_corpus() -> dict:
    """Cuánto del corpus está contrastado contra fuente oficial.

    Se cuentan solo las normas que guardan el TEXTO de algún artículo, que son
    las que se pueden citar entre comillas y por tanto las que hay que haber
    verificado. Una norma que solo tiene nombre y título no se cita literal.
    """
    try:
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        verificadas = sin_verificar = 0
        for norma in _TODAS_LAS_NORMAS.values():
            arts = norma.get("articulos") or {}
            if not any(isinstance(d, dict) and d.get("texto") for d in arts.values()):
                continue
            if norma.get("verificada"):
                verificadas += 1
            else:
                sin_verificar += 1
        return {
            "normas_verificadas": verificadas,
            "normas_sin_verificar": sin_verificar,
            "leyenda": (
                f"{verificadas} normas contrastadas contra fuente oficial"
                + (
                    f" · {sin_verificar} SIN CONTRASTAR"
                    if sin_verificar
                    else " · ninguna sin contrastar"
                )
            ),
        }
    except Exception:  # pragma: no cover - sin corpus no se promete nada
        return {"normas_verificadas": 0, "normas_sin_verificar": 0, "leyenda": ""}


def _norma_sucesora_ya_nombrada(derogada_por: str, texto: str) -> bool:
    """¿El dictamen ya nombra la norma que reemplazó a la derogada?

    `derogada_por` viene del corpus con una frase del estilo «derogada por la
    Resolución 948 de 2026 (14 de mayo)». Se saca de ahí el número y el año y
    se busca esa pareja en el dictamen. Si está, el lector ya tiene la
    información y el aviso solo hace ruido.
    """
    if not derogada_por or not texto:
        return False
    # La frase del corpus es prosa: «la derogó la Resolución 948 del 14 de
    # mayo de 2026, que rige desde su expedición (junto con las Resoluciones
    # 558 y 1884 de 2024)». Hay que engancharse al número que sigue al tipo
    # de norma —948— y no al primer par número+año que aparezca, que sería
    # el 1884 de 2024 y no es la sucesora.
    m = re.search(
        r"(?:resoluci[oó]n|ley|decreto|circular|acuerdo)\s+(\d{2,5})\b"
        r"[^.;]{0,60}?\b((?:19|20)\d{2})\b",
        derogada_por,
        re.IGNORECASE,
    )
    if not m:
        return False
    numero, anio = m.group(1), m.group(2)
    return bool(
        re.search(
            rf"\b{re.escape(numero)}\s*(?:de|/)\s*{re.escape(anio)}\b",
            texto,
            re.IGNORECASE,
        )
    )


def _verificar_folios(texto: str, issues: list[dict], evidencia: Optional[str]) -> None:
    """Marca los folios que el dictamen cita y que no están en el expediente.

    Caso real 20-08-2026. Los CUPS y los soportes ya se verificaban, pero los
    FOLIOS no: el dictamen podía escribir «SEGÚN CONSTA EN EL FOLIO 25 DE LA
    HISTORIA CLÍNICA» sin que nadie hubiera abierto una historia clínica, y
    salía sellado con «citas verificadas · 0 hallazgos».

    Es la afirmación más fácil de tumbar que hay: la EPS pide el folio 25, no
    está, ratifica la glosa completa — y en el expediente queda una
    afirmación documental falsa firmada por el hospital.

    Por qué la revisión es confiable: la IA y este verificador leen EL MISMO
    texto. Si el folio no aparece en lo que la IA tuvo a la vista, la IA no lo
    leyó — se lo inventó.

    `evidencia` es ese texto (contexto de los PDF + texto de la glosa):
      · None  → el llamador no lo aportó; no se revisa (no se inventa un fallo).
      · ""    → no se leyó ningún soporte: CUALQUIER folio citado es inventado.
      · texto → se comparan uno a uno.
    """
    # `None` NO es lo mismo que `""`:
    #   ""   → «se analizó sin adjuntar nada»  → se revisa y se marca.
    #   None → «este camino no sabe qué se leyó» → no se opina.
    #
    # 21-08-2026. Dos llamadores pasan None a propósito y hay que dejarlos así:
    #
    #   · quality_gate/post_validator.check_citas_verificadas — solo recibe el
    #     texto y la EPS; no tiene el contexto de los PDF.
    #   · dictamen_postprocesor — BORRA las frases con citas inválidas. Si acá
    #     se marcaran afirmaciones documentales, borraría argumentación clínica
    #     legítima de dictámenes donde SÍ se adjuntaron soportes.
    #
    # Pasarles `""` para «cerrar el hueco» convertiría esto en una máquina de
    # avisos falsos, y un aviso equivocado en cada dictamen enseña al auditor a
    # ignorar los avisos. La protección de verdad corre en el camino de
    # GlosaService.analizar, que sí sabe qué se leyó.
    if evidencia is None:
        return
    try:
        from app.services.extractor_folios import folios_inventados
    except Exception:  # pragma: no cover - sin el extractor no se inventa un fallo
        return

    inventados = folios_inventados(texto or "", evidencia)
    if not inventados:
        return

    listado = ", ".join(str(f) for f in inventados[:8])
    if len(inventados) > 8:
        listado += f" (y {len(inventados) - 8} más)"
    plural = len(inventados) > 1
    sin_soportes = not (evidencia or "").strip()
    issues.append(
        {
            "tipo": "FOLIO_INVENTADO",
            "severidad": "ALTA",
            "cita": f"Folio{'s' if plural else ''} {listado}",
            "detalle": (
                (
                    f"El dictamen cita el{'os' if plural else ''} folio{'s' if plural else ''} "
                    f"{listado}, pero en este análisis NO se leyó ningún soporte: no había de "
                    "dónde sacar ese número."
                )
                if sin_soportes
                else (
                    f"El dictamen cita el{'os' if plural else ''} folio{'s' if plural else ''} "
                    f"{listado} y no aparece{'n' if plural else ''} en los soportes leídos del "
                    "expediente."
                )
            )
            + " La EPS pide ese folio, no lo encuentra y ratifica la glosa completa.",
            "sugerencia": (
                (
                    # Sin un solo soporte leído no sirve mandarlo a escribir
                    # «LA HISTORIA CLÍNICA ACREDITA…»: sería cambiar una
                    # afirmación sin respaldo por otra.
                    "Adjunte el soporte y vuelva a analizar, o quite la referencia "
                    "documental: sin soportes a la vista el dictamen no puede afirmar "
                    "qué dice la historia clínica, ni con folio ni sin él."
                )
                if sin_soportes
                else (
                    "Quite el número de folio y deje la referencia al documento "
                    "(«LA HISTORIA CLÍNICA ACREDITA...»), o adjunte el soporte donde "
                    "sí conste ese folio y vuelva a analizar."
                )
            ),
        }
    )


def _verificar_afirmaciones_documentales(
    texto: str, issues: list[dict], evidencia: Optional[str]
) -> None:
    """Marca lo que el dictamen afirma que dice un documento que nadie leyó.

    Caso real 20-08-2026 (CL0801, AXA COLPATRIA). Yesid analizó una glosa de
    pertinencia SIN adjuntar un solo soporte y el dictamen salió diciendo:

        «…CUMPLE CON LOS CRITERIOS CLÍNICOS DEL MÉDICO TRATANTE, QUIEN
         DOCUMENTÓ LA INDICACIÓN EN LA HISTORIA CLÍNICA INTEGRAL.»

    Sin citar folio, así que la verificación de folios lo dejaba pasar y salía
    con «7 citas contra corpus · 0 hallazgos» y el sello del Quality Gate.

    Es la misma mentira sin el número. En una glosa de pertinencia, lo que
    dice la historia clínica ES el punto en disputa: la EPS la pide, ve que la
    afirmación no sale de ahí, y ratifica.

    Solo se revisa cuando NO se leyó expediente. Con soportes a la vista haría
    falta leerlos de verdad para saber si la frase es fiel, y marcar por las
    dudas enseñaría al auditor a ignorar los avisos.
    """
    if evidencia is None:
        return
    try:
        from app.services.extractor_folios import afirmaciones_documentales_sin_respaldo
    except Exception:  # pragma: no cover - sin el extractor no se inventa un fallo
        return

    afirmaciones = afirmaciones_documentales_sin_respaldo(texto or "", evidencia)
    if not afirmaciones:
        return

    plural = len(afirmaciones) > 1
    issues.append(
        {
            "tipo": "AFIRMACION_SIN_SOPORTE",
            "severidad": "ALTA",
            "cita": afirmaciones[0][:160],
            "detalle": (
                f"El dictamen afirma lo que dice{'n' if plural else ''} un documento "
                "clínico, pero en este análisis NO se leyó ningún soporte. El hospital "
                "estaría certificando ante la EPS el contenido de una historia clínica "
                "que nadie abrió" + (f" ({len(afirmaciones)} frases)." if plural else ".")
            ),
            "sugerencia": (
                "Adjunte el soporte y vuelva a analizar —así la afirmación queda "
                "respaldada—, o redacte sin afirmar contenido: pida a la EPS que "
                "precise qué echa de menos y ofrezca el documento, sin decir qué dice."
            ),
        }
    )


# ── Atribuirle a un artículo real un contenido que no es suyo ────────────
#
# POR QUÉ (24-08-2026). Una auditoría independiente de nueve dictámenes
# encontró que el Art. 57 de la Ley 1438 de 2011 se citó en tres expedientes
# (GL-190, GL-192 y GL-195) con TRES contenidos distintos, y ninguno es el
# suyo: «las decisiones de facturación son definitivas y no admiten recurso»,
# «la carga de la prueba corresponde a la entidad que impone la glosa» y «la
# carga de la prueba recae en la entidad». El Art. 57 real regula el trámite
# y los plazos de las glosas — 20 días hábiles para glosar, 15 para responder,
# 10 para decidir — y no dice una palabra ni de firmeza ni de prueba.
#
# El corpus del sistema NO tiene el error: se revisó y el Art. 57 guardado es
# el correcto. La invención ocurre al redactar.
#
# Las redes que ya existían solo miran lo que va ENTRE COMILLAS. Estas tres
# atribuciones iban sin comillas, parafraseadas, así que pasaron por las
# cuatro revisiones y el dictamen salió sellado como verificado.
#
# CÓMO SE ATRAPA SIN INVENTAR. No se puede exigir que una paráfrasis use las
# mismas palabras del artículo — parafrasear es legítimo. Pero una doctrina
# jurídica CON NOMBRE PROPIO es distinta: si un artículo de verdad reparte la
# carga de la prueba, su texto la nombra. Entonces la regla es estrecha y
# comprobable: cuando el dictamen dice que un artículo concreto «establece»
# una de estas doctrinas, se va al texto real de ESE artículo en el corpus y
# se mira si la nombra. Si no la nombra, se avisa. Nada más se revisa: una
# paráfrasis que no invoca ninguna doctrina con nombre no se toca.
#
# (nombre para el auditor, cómo se nombra en el dictamen, huella en el texto real)
DOCTRINAS_CON_NOMBRE: tuple[tuple[str, str, str], ...] = (
    (
        "la carga de la prueba",
        r"CARGA\s+DE\s+LA\s+PRUEBA|INVERSI[ÓO]N\s+DE\s+LA\s+CARGA",
        r"carga de la prueba|probatori|onus probandi",
    ),
    (
        "la firmeza de la decisión (que no admite recurso)",
        r"NO\s+ADMITEN?\s+RECURSO|IRRECURRIBLE|INIMPUGNABLE|"
        r"QUEDAN?\s+EN\s+FIRME|SON\s+DEFINITIVAS?\s+Y\s+NO",
        r"recurso|en firme|irrecurrible|inimpugnable|ejecutori",
    ),
    (
        "el silencio administrativo positivo",
        r"SILENCIO\s+ADMINISTRATIVO",
        r"silencio",
    ),
    (
        "la responsabilidad solidaria",
        r"RESPONSABILIDAD\s+SOLIDARIA|SOLIDARIAMENTE\s+RESPONSABLES?",
        r"solidar",
    ),
    ("la caducidad", r"\bCADUCIDAD\b", r"caducidad"),
    ("la prescripción", r"\bPRESCRIPCI[ÓO]N\b", r"prescripci"),
    (
        "la nulidad de pleno derecho",
        r"NULIDAD\s+DE\s+PLENO\s+DERECHO|NULIDAD\s+ABSOLUTA",
        r"nulidad",
    ),
    (
        "la presunción de veracidad, legalidad o buena fe",
        r"PRESUNCI[ÓO]N\s+DE\s+(?:VERACIDAD|LEGALIDAD|BUENA\s+FE)",
        r"presunci",
    ),
)

# 25-08-2026 (3.ª auditoría). El dictamen GL-127 dijo «LA LEY 1438/2011 ART. 57
# IMPONE QUE LA CARGA DE LA PRUEBA RECAE EN LA EPS» y esta red no lo vio: la
# tabla de doctrinas SÍ tenía «carga de la prueba», pero el verbo «IMPONE» no
# estaba en esta lista, así que el patrón ni siquiera enganchaba la frase.
# Mismo tipo de agujero que el del conector comido: la defensa existía y una
# palabra de menos la dejaba pasar. Se agregan los verbos que aparecieron en
# los dictámenes reales (IMPONE, FIJA, OTORGA, EXIGE, OBLIGA...).
_VERBOS_DE_ATRIBUCION = (
    r"ESTABLECE|ESTABLECEN|DISPONE|DISPONEN|SEÑALA|SENALA|CONSAGRA|INDICA|"
    r"IMPONE|IMPONEN|FIJA|FIJAN|OTORGA|OTORGAN|EXIGE|EXIGEN|OBLIGA|OBLIGAN|"
    r"GARANTIZA|GARANTIZAN|FACULTA|AUTORIZA|RECONOCE|ATRIBUYE|CONFIERE|"
    r"PRECEPT[ÚU]A|PREV[ÉE]|CONTEMPLA|ORDENA|DETERMINA|ESTIPULA|REZA|"
    r"PRESCRIBE|CONFORME\s+AL\s+CUAL|SEG[ÚU]N\s+EL\s+CUAL"
)

_NORMAS_CITABLES = r"LEY|DECRETO|RESOLUCI[ÓO]N|CIRCULAR|ACUERDO"

# Forma 1: «Art. 57 de la Ley 1438 de 2011, que establece que ...»
PAT_ATRIBUCION_ART_PRIMERO = re.compile(
    r"(?:ART[ÍI]?CULOS?|ARTS?)\.?\s*(\d{1,4})\s*"
    r"(?:DE\s+)?(?:LA\s+|EL\s+)?"
    r"(" + _NORMAS_CITABLES + r")\s*(?:N[oº°.]?\s*)?(\d{1,5})"
    r"\s*(?:DE\s+|\s*[/\-]\s*)(\d{2,4})"
    r"[^.;]{0,40}?[,\s]+(?:QUE\s+)?(?:" + _VERBOS_DE_ATRIBUCION + r")\b"
    r"\s*(?:QUE\s*)?:?\s*"
    r"([^.;]{10,400})",
    re.IGNORECASE,
)

# Forma 2: «La Ley 1438 de 2011, en su artículo 57, establece que ...»
PAT_ATRIBUCION_NORMA_PRIMERO = re.compile(
    r"(" + _NORMAS_CITABLES + r")\s*(?:N[oº°.]?\s*)?(\d{1,5})"
    r"\s*(?:DE\s+|\s*[/\-]\s*)(\d{2,4})"
    r"[,\s]+EN\s+SU\s+(?:ART[ÍI]?CULO|ART)\.?\s*(\d{1,4})"
    r"[^.;]{0,40}?[,\s]+(?:QUE\s+)?(?:" + _VERBOS_DE_ATRIBUCION + r")\b"
    r"\s*(?:QUE\s*)?:?\s*"
    r"([^.;]{10,400})",
    re.IGNORECASE,
)


# Forma 3 (25-08-2026, GL-127): «La Ley 1438/2011 Art. 57 impone que ...» —
# la norma primero y el artículo pegado detrás, SIN el «en su». Las dos formas
# de arriba no la cubrían, así que la atribución falsa de ese dictamen pasó
# derecho hasta el papel. Es la tercera vez en el día que un patrón demasiado
# estrecho deja pasar un defecto que la defensa ya sabía detectar.
PAT_ATRIBUCION_NORMA_ART_PEGADO = re.compile(
    r"(" + _NORMAS_CITABLES + r")\s*(?:N[oº°.]?\s*)?(\d{1,5})"
    r"\s*(?:DE\s+|\s*[/\-]\s*)(\d{2,4})"
    r"[,\s]+(?:ART[ÍI]?CULOS?|ARTS?)\.?\s*(\d{1,4})"
    r"[^.;]{0,40}?[,\s]+(?:QUE\s+)?(?:" + _VERBOS_DE_ATRIBUCION + r")\b"
    r"\s*(?:QUE\s*)?:?\s*"
    r"([^.;]{10,400})",
    re.IGNORECASE,
)


def _texto_real_del_articulo(
    tipo: str, numero: str, anio: str, art: str, normas: dict
) -> Optional[str]:
    """Devuelve el texto de LA NORMA para ese artículo, o None si no se puede.

    Se exige que el artículo traiga cuerpo de verdad (200 caracteres): contra
    un resumen de dos renglones no se puede afirmar que algo «no está», y
    acusar en falso es peor que no revisar.

    25-08-2026 — SOLO EL EPÍGRAFE Y EL TEXTO DE LA NORMA. Antes esta función
    devolvía también los campos «aplicacion» y «keywords», que son comentario
    NUESTRO sobre cómo usar el artículo, no la ley.

    Eso volvía la revisión inútil por el peor camino: al artículo 57 de la Ley
    1438 se le puso una nota que dice «NO le atribuya la carga de la prueba: el
    artículo no la menciona» — y esa nota, al concatenarse, hacía que la malla
    encontrara «carga de la prueba» en lo que creía ser el texto legal y diera
    por buena justo la atribución que la nota prohibía.

    Es la misma autocertificación que este motor lleva todo el día corrigiendo,
    en su versión más incómoda: la advertencia se desactivaba a sí misma.
    """
    clave = _buscar_clave_norma(tipo[:3].lower(), numero, anio, normas)
    if not clave:
        return None
    articulos = (normas.get(clave) or {}).get("articulos") or {}
    datos = None
    for k, v in articulos.items():
        if str(k) == str(art):
            datos = v
            break
    if not isinstance(datos, dict):
        return None
    cuerpo = " ".join(str(datos.get(campo) or "") for campo in ("titulo", "texto"))
    return cuerpo if len(cuerpo) >= 200 else None


def _lo_que_se_le_atribuye(contenido: str) -> str:
    """Recorta la frase a lo que el artículo de verdad «establece».

    Hace falta para no acusar en falso. En una frase como

        «conforme al Art. 21, que establece el trámite de glosas, la carga
         de la prueba corresponde a la EPS»

    al artículo se le atribuye SOLO «el trámite de glosas»; lo que va después
    de la coma es otra afirmación del redactor. Sin este recorte se marcaría un
    dictamen correcto — y una alarma en falso sobre un documento que se radica
    ante la EPS es peor que no revisar, porque enseña al auditor a no creerle a
    las alarmas.

    Distinguir las dos formas es cuestión de una coma. El inciso ABRE con coma:

        «establece que, en el trámite de glosas, la carga de la prueba…»
                      ↑ acá empieza un paréntesis; lo atribuido viene después

    mientras que la segunda oración NO:

        «establece el trámite de glosas, la carga de la prueba…»
                     ↑ esto es lo atribuido; lo de después ya es otra cosa
    """
    texto = (contenido or "").strip()
    if not texto.startswith(","):
        return texto.split(",")[0].strip()
    # Abre con coma: es un inciso. Lo atribuido viene después de cerrarlo.
    partes = [p.strip() for p in texto.split(",")]
    despues_del_inciso = ", ".join(p for p in partes[2:] if p).strip()
    return despues_del_inciso or " ".join(p for p in partes[1:] if p).strip()


def _verificar_atribuciones(texto: str, issues: list[dict], normas: dict) -> int:
    """Revisa que lo que el dictamen le atribuye a un artículo sea suyo.

    Devuelve cuántas atribuciones alcanzó a revisar, para que el contador de
    «citas verificadas» diga la verdad sobre el trabajo hecho.
    """
    revisadas = 0
    vistas: set[str] = set()
    candidatas: list[tuple[str, str, str, str, str]] = []
    for m in PAT_ATRIBUCION_ART_PRIMERO.finditer(texto):
        art, tipo, numero, anio, contenido = m.groups()
        candidatas.append((art, tipo, numero, anio, contenido))
    for m in PAT_ATRIBUCION_NORMA_PRIMERO.finditer(texto):
        tipo, numero, anio, art, contenido = m.groups()
        candidatas.append((art, tipo, numero, anio, contenido))
    for m in PAT_ATRIBUCION_NORMA_ART_PEGADO.finditer(texto):
        tipo, numero, anio, art, contenido = m.groups()
        candidatas.append((art, tipo, numero, anio, contenido))

    for art, tipo, numero, anio, contenido in candidatas:
        if len(anio) == 2:
            anio = "20" + anio if int(anio) < 50 else "19" + anio
        real = _texto_real_del_articulo(tipo, numero, anio, art, normas)
        if real is None:
            continue  # sin texto real no hay con qué comparar: otras redes lo miran
        revisadas += 1
        real_norm = _normalizar(real)
        atribuido = _lo_que_se_le_atribuye(contenido)
        for nombre, como_se_nombra, huella in DOCTRINAS_CON_NOMBRE:
            if not re.search(como_se_nombra, atribuido, re.IGNORECASE):
                continue
            if re.search(huella, real_norm, re.IGNORECASE):
                continue  # el artículo sí trata de eso: la atribución se sostiene
            firma = f"{tipo.upper()}|{numero}|{anio}|{art}|{nombre}"
            if firma in vistas:
                continue
            vistas.add(firma)
            frase = atribuido.strip()
            issues.append(
                {
                    "tipo": "ATRIBUCION_FALSA",
                    "severidad": "ALTA",
                    "cita": f"Art. {art} {tipo.title()} {numero}/{anio}",
                    "detalle": (
                        f"El dictamen dice que el Art. {art} de la {tipo.lower()} "
                        f"{numero} de {anio} trata sobre {nombre}, y el texto real de "
                        f"ese artículo no lo menciona. Lo atribuido: "
                        f"«{frase[:180]}{'...' if len(frase) > 180 else ''}»."
                    ),
                    "sugerencia": (
                        f"Cita el artículo que de verdad regula {nombre}, o quita esa "
                        f"atribución y usa el Art. {art} para lo que sí dice. Radicado "
                        "así, la EPS puede desmontar el argumento mostrando el texto."
                    ),
                }
            )
    return revisadas


def verificar_citas(
    dictamen_html: str,
    eps: Optional[str] = None,
    evidencia: Optional[str] = None,
) -> dict:
    """Escanea el dictamen y devuelve un reporte de validación.

    Estructura:
        {
          "total_citas": int,
          "ok": int,
          "issues": [
            {
              "tipo": "NORMA_INEXISTENTE" | "ARTICULO_FUERA_DE_NORMA"
                      | "CITA_LITERAL_FALSA" | "CITA_VACIA"
                      | "CUPS_INEXISTENTE" | "FOLIO_INVENTADO",
              "severidad": "ALTA" | "MEDIA" | "BAJA",
              "cita": str,      # lo que aparece en el dictamen
              "detalle": str,   # explicación
              "sugerencia": str | None,
            }
          ],
          "tiene_problemas_graves": bool,  # alguna severidad ALTA
        }

    `evidencia` es el texto que la IA tuvo a la vista para redactar (contexto
    de los PDF + texto de la glosa). Si no se pasa, los folios NO se revisan:
    sin saber qué leyó la IA no se puede decir que inventó nada.

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
                            # 27-08-2026 — «NO LA TENGO» NO ES «NO EXISTE».
                            # El dictamen GL-135 citó la Resolución 839 de 2017
                            # y esto la marcó NORMA_INEXISTENTE en severidad
                            # ALTA. Verificada contra el normograma oficial de
                            # la Supersalud, esa resolución EXISTE: es conjunta
                            # de MinSalud y MinCultura y modifica justamente la
                            # Res. 1995 de 1999 que el mismo dictamen cita.
                            # O sea que el sello le decía al auditor que una
                            # norma real y pertinente era inventada — el error
                            # exactamente contrario al que este revisor existe
                            # para evitar, y el que más rápido le quita la
                            # credibilidad al sello.
                            # El corpus tiene 26 normas de las miles que hay:
                            # que una no esté cargada no dice nada sobre si
                            # existe. Se avisa, en severidad media, con lo
                            # único que este revisor puede afirmar.
                            **_falta_del_corpus(tipo_label, numero, anio),
                        }
                    )
                elif normas[clave].get("vigente") is False:
                    # LA NORMA EXISTE PERO YA NO RIGE (24-08-2026).
                    #
                    # El corpus tenía desde siempre un campo que dice si la
                    # norma sigue vigente, y nadie lo miraba: un dictamen podía
                    # apoyarse en una resolución derogada y salir con cero
                    # hallazgos. Se descubrió revisando la Resolución 2275 de
                    # 2023 —la de factura electrónica y RIPS, que el motor cita
                    # en varios sitios—: la derogó la Resolución 948 del 14 de
                    # mayo de 2026, y el motor la seguía dando por vigente.
                    #
                    # El aviso es MEDIA y no ALTA a propósito: si el servicio
                    # se prestó mientras la norma regía, citarla puede ser lo
                    # correcto. Quien sabe la fecha del servicio es el gestor,
                    # así que se le avisa y él decide.
                    _nota = (normas[clave].get("derogada_por") or "").strip()
                    # 25-08-2026: si el propio dictamen ya dice cuál norma la
                    # reemplazó y desde cuándo, el aviso sobra. En el lote de
                    # recepción del día salieron 21 avisos por la Res. 2275 de
                    # 2023 — y el gestor que ve 21 avisos de algo que el texto
                    # ya explica deja de leerlos todos. Se exige que el
                    # dictamen nombre la sucesora, no solo que hable de fechas.
                    if _nota and _norma_sucesora_ya_nombrada(_nota, texto):
                        continue
                    issues.append(
                        {
                            "tipo": "NORMA_DEROGADA",
                            "severidad": "MEDIA",
                            "cita": f"{tipo_label} {numero} de {anio}",
                            "detalle": (
                                f"La {tipo_label} {numero} de {anio} ya no está vigente"
                                + (f": {_nota}" if _nota else ".")
                                + " Si el servicio se prestó mientras regía, citarla puede "
                                "ser correcto; si es posterior, la EPS puede desmontar el "
                                "argumento mostrando la derogatoria."
                            ),
                            "sugerencia": (
                                "Revise la fecha del servicio. Si es posterior a la "
                                "derogatoria, cite la norma que la reemplazó."
                            ),
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
                    "sugerencia": "Verifica que la sentencia exista o reemplaza por una verificada (ej: T-760/2008).",
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
                # QUE NO ESTÉ AQUÍ NO SIGNIFICA QUE NO EXISTA (24-08-2026).
                #
                # El corpus guarda 131 normas y solo 26 tienen algún artículo
                # cargado; la que más tiene, cuatro. De la Ley 100 de 1993 están
                # el 168, el 177 y el 178 — tres de casi trescientos.
                #
                # Aun así, este aviso decía «la norma no contiene el artículo» y
                # el limpiador de dictámenes borra la ORACIÓN ENTERA que lo
                # menciona. Reproducido ese día: un dictamen que citaba el
                # Art. 156 de la Ley 100 —artículo real y de los cimientos del
                # sistema— salía sin esa frase. O sea: el motor le quitaba al
                # documento que se radica ante la EPS un argumento correcto, sin
                # decírselo a nadie.
                #
                # Ahora solo se afirma que el artículo no existe cuando de la
                # norma se cargó su lista COMPLETA de artículos, que es cuando
                # de verdad se puede afirmar. Si la lista es parcial, se avisa
                # con severidad baja y sin borrar nada: «no se pudo verificar».
                completa = bool(n.get("articulos_completos"))
                if completa:
                    issues.append(
                        {
                            "tipo": "ARTICULO_FUERA_DE_NORMA",
                            "severidad": "MEDIA",
                            "cita": f"Art. {art_num} {norma_tipo} {norma_num}/{norma_anio}",
                            "detalle": (
                                f"La {norma_tipo} {norma_num}/{norma_anio} no contiene el "
                                f"Art. {art_num}. De esta norma el sistema tiene cargados "
                                "todos sus artículos, así que el número está mal."
                            ),
                            "sugerencia": "Verifica el número de artículo o consulta los artículos disponibles de esta norma.",
                        }
                    )
                elif arts:
                    issues.append(
                        {
                            "tipo": "ARTICULO_NO_VERIFICABLE",
                            "severidad": "BAJA",
                            "cita": f"Art. {art_num} {norma_tipo} {norma_num}/{norma_anio}",
                            "detalle": (
                                f"De la {norma_tipo} {norma_num}/{norma_anio} el sistema solo "
                                f"tiene cargados {len(arts)} artículo(s), y el {art_num} no "
                                "está entre ellos. Puede ser correcto: no hay con qué "
                                "comprobarlo. Verifíquelo a mano antes de radicar."
                            ),
                            "sugerencia": (
                                "Confirme el número contra el texto oficial de la norma, o "
                                "cargue ese artículo al corpus para que quede verificado."
                            ),
                        }
                    )

    # 3b. Contenido atribuido a un artículo real que ese artículo no tiene.
    total_citas += _verificar_atribuciones(texto, issues, normas)

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

    # 7. Folios que el dictamen afirma y que no están en el expediente leído.
    _verificar_folios(texto, issues, evidencia)
    _verificar_afirmaciones_documentales(texto, issues, evidencia)
    if evidencia is not None:
        from app.services.extractor_folios import folios_citados as _fc

        total_citas += len(_fc(texto))

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
        # 26-08-2026: el sello decía «N citas contra corpus · 0 hallazgos» sin
        # decir NUNCA qué tan de fiar es ese corpus. Esa semana se descubrió
        # que 21 de las 26 normas guardadas tenían algún artículo con el nombre
        # o el texto inventado — o sea que el sello estuvo meses certificando
        # contra una lista que nadie había contrastado.
        # Ahora el sello lleva su propia hoja de vida.
        "corpus": _estado_del_corpus(),
    }
