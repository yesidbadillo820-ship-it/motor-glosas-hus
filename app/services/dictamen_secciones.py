"""División del dictamen multi-código en secciones por código (jun-2026).

Origen ("Opción A" del Excel radicable, 12-jun-2026): las glosas
multi-código guardan UN solo dictamen con las respuestas de todos los
códigos concatenadas (multi_codigo.py, PR #104). El Excel radicable pinta
una fila por ConceptoGlosaRecord, pero como el campo por-concepto
(`dictamen_html`) casi siempre está vacío, TODAS las filas de la misma
factura caían al `glosa.dictamen` completo: en el export del dueño las
filas 4 (AU0101) y 100 (CO0701) salían palabra por palabra idénticas,
ambas encabezadas por el bloque de TA0101.

Este módulo es el fix de PRESENTACIÓN: divide ese dictamen por los
separadores reales que produce multi_codigo._wrap_seccion_html —

    ═══ RESPUESTA AL CÓDIGO {CODIGO} — {FAMILIA} ═══

— y devuelve solo la sección del código pedido. Funciona tanto sobre el
HTML almacenado como sobre su versión texto plano (dictamen_a_texto_plano
conserva el título «═══ …» como línea legible). No toca el flujo de
análisis ni la BD: cero IA, cero dependencias externas, solo `re` y
lógica de strings.
"""

import re

__all__ = [
    "extraer_codigo_principal_del_dictamen",
    "extraer_seccion_por_codigo",
    "indice_codigos_del_dictamen",
]

# Separador real de multi_codigo._wrap_seccion_html:
#   "═══ RESPUESTA AL CÓDIGO TA0201 — TARIFAS ═══"
# Tolerancias deliberadas (casos vistos en exports/copias): espacios extra
# alrededor de los «═══», minúsculas, código con espacio o guion interno
# ("TA 0201"), familia sin guion o ausente, cierre «═══» perdido por un
# recorte. El fence acepta también "==" ASCII por si el texto pasó por un
# editor que no conserva U+2550.
_PAT_SEPARADOR = re.compile(
    r"[═=]{2,}\s*RESPUESTA\s+AL\s+C[OÓ]DIGO\s*:?\s*"
    r"([A-Za-z]{2})\s*[-–—]?\s*(\d{4})"
    r"(?:[^═=<>\n]{0,80}?[═=]{2,})?",
    re.IGNORECASE,
)

# Marca de la tabla de cabecera del dictamen principal (glosa_service):
#   HTML:  <th>CÓDIGO GLOSA</th> … <td>TA0801</td>
#   texto: "CÓDIGO GLOSA: TA0801 | VALOR OBJETADO: …"
# El «CÓDIGOS GLOSA: …» (plural) del encabezado multi-código NO matchea:
# la S pegada a CÓDIGO rompe el \s+ obligatorio.
_PAT_MARCA_PRINCIPAL = re.compile(r"\bC[OÓ]DIGO\s+GLOSA\b", re.IGNORECASE)
_PAT_CODIGO_SUELTO = re.compile(r"\b([A-Za-z]{2})[-\s]?(\d{4})\b")

# Pie de firma/sello QG que el render radicable (static/index.html) anexa
# al final del documento. Si el texto recibido lo trae, la ÚLTIMA sección
# se corta ahí para que el pie no quede pegado (ni duplicado) en una
# sección secundaria.
_PAT_PIE_FIRMA = re.compile(
    r"[ÁA]rea\s+de\s+Cartera"
    r"|Generado\s+por\s+IA\s+con\s+Quality\s+Gate"
    r"|Firma\s+autorizada\s+ESE\s+HUS",
    re.IGNORECASE,
)

_PAT_TAG = re.compile(r"<[^>]+>")


def _normalizar_codigo(codigo: str | None) -> str:
    """«ta 02-01» → «TA0201» (comparación insensible a espacios/guiones)."""
    return re.sub(r"[^A-Z0-9]", "", (codigo or "").upper())


def _cortar_pie_de_firma(bloque: str) -> str:
    m = _PAT_PIE_FIRMA.search(bloque)
    return bloque[: m.start()] if m else bloque


def extraer_codigo_principal_del_dictamen(dictamen: str) -> str | None:
    """Código de la tabla de cabecera («CÓDIGO GLOSA: XXNNNN»).

    Acepta el HTML almacenado (donde el código vive en un <td> aparte del
    <th>CÓDIGO GLOSA</th>) y el texto plano de dictamen_a_texto_plano.
    Devuelve None si el dictamen no trae esa tabla (texto fijo simple).
    """
    if not (dictamen or "").strip():
        return None
    # Tags fuera ANTES de buscar: los style inline traen tokens tipo
    # "#dc2626" que confundirían la búsqueda del código suelto.
    texto = _PAT_TAG.sub(" ", str(dictamen))
    m = _PAT_MARCA_PRINCIPAL.search(texto)
    if not m:
        return None
    # Ventana corta tras la marca: en ambos formatos el código aparece a
    # menos de ~60 chars (tras «VALOR OBJETADO / CÓDIGO RESPUESTA»).
    ventana = texto[m.end() : m.end() + 250]
    mc = _PAT_CODIGO_SUELTO.search(ventana)
    if not mc:
        return None
    return _normalizar_codigo(mc.group(1) + mc.group(2))


def extraer_seccion_por_codigo(
    dictamen_html_o_texto: str,
    codigo_concepto: str,
    codigo_principal: str | None = None,
) -> str | None:
    """Sección del dictamen que corresponde a `codigo_concepto`.

    Reglas (en orden):
      1. Si el código tiene su separador «═══ RESPUESTA AL CÓDIGO … ═══»,
         devuelve el bloque entre ese separador y el siguiente (o el pie
         de firma/sello QG si es la última sección).
      2. Si el código es el principal (argumento `codigo_principal` o, en
         su defecto, el de la tabla de cabecera), devuelve TODO lo que
         queda por encima del primer separador: encabezado del documento,
         tabla, ARGUMENTACIÓN JURÍDICA, cierre y nota IA. Sin separadores
         eso es el dictamen completo.
      3. Si el principal es indeterminable Y no hay separadores, no hay
         forma de dividir: se devuelve el dictamen completo (status quo —
         preferible a una nota «ver fila principal» que se apuntaría a sí
         misma).
      4. En cualquier otro caso devuelve None: el código no tiene sección
         propia en este dictamen y el caller decide el texto neutro.
    """
    d = dictamen_html_o_texto or ""
    if not d.strip():
        return None
    cod = _normalizar_codigo(codigo_concepto)
    if not cod:
        return None

    separadores = list(_PAT_SEPARADOR.finditer(d))

    # 1) ¿El código tiene separador propio?
    for i, m in enumerate(separadores):
        if _normalizar_codigo(m.group(1) + m.group(2)) != cod:
            continue
        if i + 1 < len(separadores):
            bloque = d[m.start() : separadores[i + 1].start()]
        else:
            bloque = _cortar_pie_de_firma(d[m.start() :])
        return bloque.strip() or None

    # 2) ¿Es el código principal?
    principal = _normalizar_codigo(codigo_principal) or extraer_codigo_principal_del_dictamen(d)
    if principal and cod == principal:
        bloque = d[: separadores[0].start()] if separadores else d
        return bloque.strip() or None

    # 3) Principal indeterminable y sin separadores → status quo.
    if not principal and not separadores:
        return d.strip() or None

    # 4) Código sin sección en este dictamen.
    return None


def indice_codigos_del_dictamen(dictamen: str) -> list[str]:
    """Códigos detectados en el dictamen, en orden: el principal (tabla de
    cabecera, si existe) + uno por cada separador multi-código, sin
    duplicados. Lista vacía si no se detecta ninguno."""
    d = dictamen or ""
    codigos: list[str] = []
    principal = extraer_codigo_principal_del_dictamen(d)
    if principal:
        codigos.append(principal)
    for m in _PAT_SEPARADOR.finditer(d):
        c = _normalizar_codigo(m.group(1) + m.group(2))
        if c and c not in codigos:
            codigos.append(c)
    return codigos
