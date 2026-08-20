"""
extractor_folios.py — Detecta folios, páginas y referencias documentales
=========================================================================
Analiza el texto extraído de los PDFs adjuntos para identificar:
  • Números de folio ("folio 59", "fl. 15", "hoja 23")
  • Números de página ("pág. 7", "página 3")
  • Fechas específicas (dd/mm/yyyy)
  • Firmas ("firmado por Dr. X")

Estos datos se inyectan al prompt IA para que la respuesta cite
referencias documentales específicas del expediente, haciendo la
respuesta casi imposible de ratificar por la EPS.
"""

from __future__ import annotations
import re
from collections import Counter


_PATRON_FOLIO = re.compile(
    r"(?:folio|fl\.?|hoja|página|pagina|pág\.?|pag\.?)\s*(?:no?\.?|número|num\.?)?\s*(\d{1,4})",
    re.IGNORECASE,
)
_PATRON_FECHA = re.compile(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b")
_PATRON_CIE10 = re.compile(r"\b([A-Z]\d{2}(?:\.\d)?)\b")
_PATRON_CUPS_6D = re.compile(r"\b(\d{6})\b")
_PATRON_HC = re.compile(
    r"(?:hist\.?\s*cl[íi]nica|historia\s*cl[íi]nica|HC)[\s#:]*(\d{4,12})", re.IGNORECASE
)
_PATRON_FIRMA = re.compile(
    r"(?:firmado|firma|suscrito|expedido)\s+por[\s:]*(Dr\.?\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,3})",
    re.IGNORECASE,
)


def extraer_referencias_documentales(contexto_pdf: str) -> dict:
    """Escanea el contexto PDF y retorna referencias documentales estructuradas.

    Returns:
        {
            "folios_citables": [list of int],     # folios mencionados
            "fechas_citables": [list of str],     # fechas DD/MM/YYYY
            "cie10_encontrados": [list of str],   # códigos CIE-10
            "cups_encontrados": [list of str],    # CUPS de 6 dígitos
            "historias_clinicas": [list of str],
            "firmas_medicos": [list of str],
            "resumen_citable": str,               # texto listo para prompt IA
        }
    """
    if not contexto_pdf:
        return {
            "folios_citables": [],
            "fechas_citables": [],
            "cie10_encontrados": [],
            "cups_encontrados": [],
            "historias_clinicas": [],
            "firmas_medicos": [],
            "resumen_citable": "",
        }

    # Folios (top 5 más frecuentes)
    folios = [int(m) for m in _PATRON_FOLIO.findall(contexto_pdf) if 1 <= int(m) <= 9999]
    folios_top = [f for f, _ in Counter(folios).most_common(5)]

    # Fechas (únicas)
    fechas_raw = _PATRON_FECHA.findall(contexto_pdf)
    fechas_norm = []
    for d, m, y in fechas_raw:
        try:
            dia, mes, ano = int(d), int(m), int(y)
            if len(y) == 2:
                ano = 2000 + ano if ano < 50 else 1900 + ano
            if 1 <= dia <= 31 and 1 <= mes <= 12 and 2020 <= ano <= 2030:
                fechas_norm.append(f"{dia:02d}/{mes:02d}/{ano}")
        except ValueError:
            continue
    fechas_unicas = list(dict.fromkeys(fechas_norm))[:8]

    # CIE-10
    cie10 = list(dict.fromkeys(_PATRON_CIE10.findall(contexto_pdf)))[:6]

    # CUPS
    cups = list(dict.fromkeys(_PATRON_CUPS_6D.findall(contexto_pdf)))[:10]

    # Historias clínicas
    hc = list(dict.fromkeys(_PATRON_HC.findall(contexto_pdf)))[:3]

    # Firmas
    firmas = list(dict.fromkeys(_PATRON_FIRMA.findall(contexto_pdf)))[:3]

    # Resumen citable para el prompt
    lineas = []
    if folios_top:
        lineas.append(
            f"  • Folios del expediente referenciables: {', '.join(str(f) for f in folios_top)}"
        )
    if fechas_unicas:
        lineas.append(f"  • Fechas documentales: {', '.join(fechas_unicas[:5])}")
    if hc:
        lineas.append(f"  • Historia(s) clínica(s) N°: {', '.join(hc)}")
    if firmas:
        lineas.append(f"  • Firma(s) identificada(s): {'; '.join(firmas)}")
    if cie10:
        lineas.append(f"  • Diagnóstico(s) CIE-10: {', '.join(cie10)}")
    if cups:
        lineas.append(f"  • CUPS presentes en soporte: {', '.join(cups[:5])}")

    resumen = (
        "\n".join(lineas) if lineas else "  (sin referencias documentales específicas detectadas)"
    )

    return {
        "folios_citables": folios_top,
        "fechas_citables": fechas_unicas,
        "cie10_encontrados": cie10,
        "cups_encontrados": cups,
        "historias_clinicas": hc,
        "firmas_medicos": firmas,
        "resumen_citable": resumen,
    }


# ─────────────────────────────────────────────────────────────────────────
#  VERIFICACIÓN DE FOLIOS CITADOS — 20-08-2026
#
#  Hasta hoy el motor ya no inventaba CUPS ni soportes, pero SÍ folios. Un
#  dictamen podía decir «SEGÚN CONSTA EN EL FOLIO 25 DE LA HISTORIA CLÍNICA»
#  sin que nadie hubiera abierto una historia clínica. Es la afirmación más
#  fácil de tumbar que existe: la EPS pide el folio 25, no está, y ratifica
#  la glosa completa — además de dejar en el expediente una afirmación
#  documental falsa firmada por el hospital.
#
#  La clave que hace segura la verificación: **la IA y el verificador leen
#  exactamente el mismo texto**. Si el folio no aparece en lo que la IA
#  pudo leer, la IA no lo leyó: se lo inventó.
# ─────────────────────────────────────────────────────────────────────────

# Palabras con las que un documento —o un dictamen— nombra un folio.
# El \b inicial evita que "PORTAFOLIO 5" cuente como folio.
_PALABRA_FOLIO = r"(?:folios?|fls?\.|hojas?|p[áa]ginas?|p[áa]gs?\.|pags?\.)"

# Un folio citado puede venir suelto ("FOLIO 25"), en lista ("FOLIOS 3, 5 Y 7")
# o en rango ("FOLIOS 12 AL 15"). Se capturan TODOS los números escritos; los
# rangos NO se expanden a propósito: un dictamen que dice «FOLIOS 1 A 40»
# afirma esos dos extremos, no cuarenta folios, y expandirlos llenaría la
# pantalla del auditor de avisos que no puede atender.
_PATRON_FOLIO_CITADO = re.compile(
    r"\b" + _PALABRA_FOLIO + r"\s*(?:nros?\.?|n[oº°]s?\.?|n[uú]meros?|nums?\.?)?\s*"
    r"(\d{1,4}(?:\s*(?:,|y|a|al|-|–|—|hasta)\s*\d{1,4})*)",
    re.IGNORECASE,
)


def _numeros_de(bruto: str) -> list[int]:
    """Los números escritos dentro de una lista/rango de folios."""
    return [int(n) for n in re.findall(r"\d{1,4}", bruto or "") if 1 <= int(n) <= 9999]


def folios_citados(texto: str) -> list[int]:
    """Folios que un texto AFIRMA, en orden y sin repetir.

    Se usa sobre el dictamen: es lo que el hospital le está diciendo a la EPS
    que revise.
    """
    if not texto:
        return []
    vistos: list[int] = []
    for bruto in _PATRON_FOLIO_CITADO.findall(texto):
        for n in _numeros_de(bruto):
            if n not in vistos:
                vistos.append(n)
    return vistos


def folios_en_evidencia(texto: str) -> set[int]:
    """Folios que de verdad aparecen en el texto leído del expediente.

    A diferencia de `extraer_referencias_documentales`, que devuelve solo los
    5 más frecuentes para no saturar el prompt, aquí se devuelven TODOS: si se
    comparara contra la lista recortada, un folio real pero poco repetido se
    marcaría como inventado.
    """
    if not texto:
        return set()
    return {int(m) for m in _PATRON_FOLIO.findall(texto) if 1 <= int(m) <= 9999}


def folios_inventados(dictamen: str, evidencia: str) -> list[int]:
    """Folios que el dictamen cita y que NO están en el expediente leído.

    `evidencia` es el texto que la IA tuvo a la vista (contexto de los PDF y
    el texto de la glosa). Vacío significa que no se leyó ningún soporte: ahí
    CUALQUIER folio citado es inventado, porque no había de dónde sacarlo.
    """
    citados = folios_citados(dictamen)
    if not citados:
        return []
    reales = folios_en_evidencia(evidencia)
    return [f for f in citados if f not in reales]


# ─────────────────────────────────────────────────────────────────────────
#  AFIRMACIONES DOCUMENTALES SIN RESPALDO — 20-08-2026
#
#  Hermano del control de folios, para el caso que aquel no ve. Yesid probó
#  una glosa de pertinencia (CL0801, AXA COLPATRIA) SIN adjuntar un solo
#  soporte, y el dictamen salió afirmando:
#
#      «…CUMPLE CON LOS CRITERIOS CLÍNICOS DEL MÉDICO TRATANTE, QUIEN
#       DOCUMENTÓ LA INDICACIÓN EN LA HISTORIA CLÍNICA INTEGRAL.»
#
#  Nadie abrió una historia clínica. La medalla decía «7 citas contra corpus ·
#  0 hallazgos» y el sello «VALIDADO POR QUALITY GATE». No cita ningún folio,
#  así que el control de folios la deja pasar limpia.
#
#  Es la misma mentira sin el número: el hospital certifica ante la EPS lo que
#  dice un documento que no leyó. Y en pertinencia es justo el punto en
#  disputa, así que la EPS pide la historia, ve que la afirmación no sale de
#  ahí, y ratifica.
#
#  REGLA DELIBERADAMENTE ESTRECHA: solo se marca cuando NO se leyó ningún
#  soporte. Con soportes a la vista no se puede saber sin leerlos de verdad si
#  la afirmación es fiel, y un aviso equivocado es peor que ninguno — enseña
#  al auditor a ignorar los avisos. Media verificación honesta vale más que
#  una completa que se inventa la mitad.
# ─────────────────────────────────────────────────────────────────────────

# Documentos clínicos cuyo CONTENIDO solo se puede afirmar habiéndolos leído.
_DOC_CLINICO = (
    r"(?:historias?\s+cl[íi]nicas?|epicrisis|hojas?\s+de\s+atenci[óo]n"
    r"|descripci[óo]n\s+quir[úu]rgica|hojas?\s+de\s+administraci[óo]n"
    r"|registros?\s+de\s+enfermer[íi]a|notas?\s+m[ée]dicas?"
    r"|notas?\s+de\s+evoluci[óo]n|evoluci[óo]n\s+m[ée]dica"
    r"|record\s+anest[ée]sico|f[óo]rmulas?\s+m[ée]dicas?)"
)

# Verbos con los que un dictamen AFIRMA lo que un documento dice. No entran
# los que solo lo anuncian u ofrecen ("se anexa", "se remite", "obra en el
# expediente", "está a disposición"): esos no afirman contenido.
# Se listan las formas conjugadas una por una, con y sin tilde: muchos
# dictámenes salen en mayúsculas y sin acentos. No entra "DOCUMENTAL" ni
# "DOCUMENTACIÓN" (adjetivo y sustantivo, no afirman nada).
_VERBO_AFIRMA = (
    r"(?:acredit(?:a|an|[óo]|aron)"
    r"|document(?:a|an|[óo]|aron)"
    r"|registr(?:a|an|[óo]|aron)"
    r"|consign(?:a|an|[óo]|aron)"
    r"|certific(?:a|an|[óo]|aron)"
    r"|evidenci(?:a|an|[óo]|aron)"
    r"|describ(?:e|en|i[óo])"
    r"|demuestra[n]?|reflej(?:a|an)|const(?:a|an|[óo])"
    r"|da\s+cuenta|dan\s+cuenta|deja\s+constancia"
    r"|se\s+(?:observa|evidencia|consigna|describe|registra|acredita))\b"
)

# "EL DOCUMENTO DE LA HISTORIA CLÍNICA" es un sustantivo, no una afirmación.
# Sin esta guarda, «SE APORTA EL DOCUMENTO DE LA HISTORIA CLÍNICA» —que no
# afirma ningún contenido— saldría marcado.
_NO_TRAS_ARTICULO = (
    r"(?<!\bEL )(?<!\bUN )(?<!\bDEL )(?<!\bLOS )(?<!\bel )(?<!\bun )(?<!\bdel )(?<!\blos )"
)

# «LA HISTORIA CLÍNICA ACREDITA…»  y  «…CONSTA EN LA HISTORIA CLÍNICA»
_AFIRMACION_DOCUMENTAL = re.compile(
    rf"(?:{_DOC_CLINICO}[^.;]{{0,60}}?\s{_NO_TRAS_ARTICULO}{_VERBO_AFIRMA}"
    rf"|{_NO_TRAS_ARTICULO}{_VERBO_AFIRMA}\s[^.;]{{0,60}}?"
    rf"\b(?:en|de)\s+(?:la|el|las|los)\s+{_DOC_CLINICO})",
    re.IGNORECASE,
)

# Señales de que SÍ se leyó un expediente. Si el texto que tuvo la IA a la
# vista trae cualquiera de estas, hubo documento y esta verificación se
# abstiene (la de folios sigue operando por su cuenta).
_SENAL_DE_EXPEDIENTE = re.compile(
    rf"(?:{_DOC_CLINICO}|{_PALABRA_FOLIO}\s*\d|═══\s*SOPORTE|EVIDENCIA\s+FORENSE)",
    re.IGNORECASE,
)


def se_leyo_expediente(evidencia: str) -> bool:
    """¿El texto que la IA tuvo a la vista contiene algún documento clínico?"""
    if not evidencia or not evidencia.strip():
        return False
    return bool(_SENAL_DE_EXPEDIENTE.search(evidencia))


def afirmaciones_documentales_sin_respaldo(dictamen: str, evidencia: str) -> list[str]:
    """Frases del dictamen que afirman lo que dice un documento no leído.

    Devuelve la frase completa (recortada) de cada afirmación, para que el
    auditor vea en pantalla exactamente qué se está diciendo de más. Lista
    vacía cuando sí se leyó expediente: ahí esta verificación se abstiene.
    """
    if not dictamen or se_leyo_expediente(evidencia):
        return []
    hallazgos: list[str] = []
    for frase in re.split(r"(?<=[.;])\s+", dictamen):
        if _AFIRMACION_DOCUMENTAL.search(frase):
            limpia = re.sub(r"\s+", " ", frase).strip()
            if limpia and limpia not in hallazgos:
                hallazgos.append(limpia[:300])
    return hallazgos
