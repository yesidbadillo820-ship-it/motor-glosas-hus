"""Conversión de dictámenes HTML a texto plano legible.

Los dictámenes se guardan como HTML (tabla de cabecera CÓDIGO GLOSA /
VALOR OBJETADO / CÓDIGO RESPUESTA + bloques de argumentación con
estilos inline). Ese HTML es correcto para la UI, pero cuando se vuelca
a una celda de Excel (columna RESPUESTA IA del Excel-respuesta, columna
"Dictamen HUS" del export de historial) o a un PDF radicable, el gestor
recibía `<table border="1" style=...>` literal — inservible.

Este módulo es la única fuente de verdad para esa conversión:

  - `dictamen_a_texto_plano(html)` → texto limpio con saltos de línea
    sensatos. Las tablas se convierten a líneas legibles tipo
    "CÓDIGO GLOSA: TA0801 | VALOR OBJETADO: $36.402 | CÓDIGO RESPUESTA:
    RE9901". Idempotente: texto ya plano pasa sin romperse.
  - `tabla_a_filas(html_tabla)` → matriz de celdas de texto (la usa el
    PDF radicable para reconstruir la tabla de cabecera en reportlab).
  - `extraer_tabla_cabecera(html)` → (filas, html_sin_esa_tabla) para
    render estructurado de la primera tabla del dictamen.
"""

import html as _html
import re

__all__ = [
    "dictamen_a_texto_plano",
    "tabla_a_filas",
    "extraer_tabla_cabecera",
]

PAT_TABLE = re.compile(r"<table[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_PAT_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_PAT_CELDA = re.compile(r"<(td|th)[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_PAT_TAG = re.compile(r"<[^>]+>")


def _texto_celda(html_celda: str) -> str:
    """Texto plano de una celda: tags fuera, entities decodificadas,
    espacios colapsados (los <br> internos pasan a espacio simple)."""
    txt = re.sub(r"<br\s*/?>", " ", html_celda or "", flags=re.IGNORECASE)
    txt = _PAT_TAG.sub(" ", txt)
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def tabla_a_filas(html_tabla: str) -> list[list[str]]:
    """Convierte un `<table>...</table>` en matriz de celdas de texto.

    Filas sin ninguna celda con contenido se descartan (separadores
    visuales, filas de línea decorativa, etc.).
    """
    filas: list[list[str]] = []
    for m in _PAT_TR.finditer(html_tabla or ""):
        celdas = [_texto_celda(c) for _tag, c in _PAT_CELDA.findall(m.group(1))]
        if any(celdas):
            filas.append(celdas)
    return filas


def _primera_fila_es_encabezado(html_tabla: str) -> bool:
    """True si la primera <tr> con contenido usa celdas <th>."""
    for m in _PAT_TR.finditer(html_tabla or ""):
        celdas = _PAT_CELDA.findall(m.group(1))
        if not celdas:
            continue
        if any(_texto_celda(c) for _tag, c in celdas):
            return any(tag.lower() == "th" for tag, _c in celdas)
    return False


def _tabla_a_lineas(html_tabla: str) -> str:
    """Tabla HTML → líneas de texto legibles.

    Si la primera fila son encabezados (<th>), cada fila de datos sale
    como "HEADER1: valor1 | HEADER2: valor2 | ...". Filas con distinto
    número de celdas (p. ej. la fila de trazabilidad con colspan=3)
    salen como línea propia con sus celdas unidas por " | ".
    """
    filas = tabla_a_filas(html_tabla)
    if not filas:
        return ""
    encabezados: list[str] | None = None
    datos = filas
    if _primera_fila_es_encabezado(html_tabla) and len(filas) >= 2:
        encabezados = filas[0]
        datos = filas[1:]
    lineas = []
    for fila in datos:
        celdas = [c for c in fila if c]
        if encabezados and len(fila) == len(encabezados):
            lineas.append(" | ".join(f"{h}: {v}" for h, v in zip(encabezados, fila) if v))
        elif celdas:
            lineas.append(" | ".join(celdas))
    return "\n".join(lineas)


def extraer_tabla_cabecera(html: str) -> tuple[list[list[str]] | None, str]:
    """Separa la PRIMERA tabla del dictamen (la cabecera CÓDIGO GLOSA /
    VALOR OBJETADO / CÓDIGO RESPUESTA) del resto del HTML.

    Devuelve (filas_de_la_tabla | None, html_restante). Si no hay tabla
    o la primera tabla no parece la cabecera, devuelve (None, html).
    """
    if not html:
        return None, ""
    m = PAT_TABLE.search(html)
    if not m:
        return None, html
    filas = tabla_a_filas(m.group(0))
    texto_tabla = " ".join(" ".join(f) for f in filas).upper()
    if "CÓDIGO GLOSA" not in texto_tabla and "CODIGO GLOSA" not in texto_tabla:
        return None, html
    resto = html[: m.start()] + html[m.end() :]
    return filas, resto


def dictamen_a_texto_plano(contenido) -> str:
    """HTML del dictamen → texto plano con saltos de línea sensatos.

    - Tablas → líneas legibles ("CÓDIGO GLOSA: TA0801 | VALOR OBJETADO:
      $36.402 | CÓDIGO RESPUESTA: RE9901").
    - <br>, </p>, </div>, </li>, </h*> → saltos de línea.
    - <li> → viñeta "• ".
    - Resto de tags eliminados, entities decodificadas.
    - Idempotente: texto sin tags HTML pasa sin alterarse (más allá de
      trim de espacios en los extremos).
    """
    if not contenido:
        return ""
    texto = str(contenido)
    if "<" not in texto:
        # Ya es texto plano — no tocar (idempotencia).
        return texto.strip()

    # 1. Tablas → líneas legibles (antes de tocar el resto de tags).
    texto = PAT_TABLE.sub(lambda m: "\n" + _tabla_a_lineas(m.group(0)) + "\n", texto)

    # 2. Tags estructurales → saltos de línea / viñetas.
    texto = re.sub(r"<br\s*/?>", "\n", texto, flags=re.IGNORECASE)
    texto = re.sub(
        r"</(p|div|section|article|h[1-6]|li|ul|ol|tr)>", "\n", texto, flags=re.IGNORECASE
    )
    texto = re.sub(r"<li[^>]*>", "• ", texto, flags=re.IGNORECASE)

    # 3. Resto de tags fuera + entities decodificadas.
    texto = _PAT_TAG.sub(" ", texto)
    texto = _html.unescape(texto)

    # 4. Normalizar espacios: colapsar horizontales, limpiar bordes de
    #    línea, máximo un renglón en blanco seguido.
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" ?\n ?", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()
