"""¿La EPS del formulario es la misma que nombra el texto de la glosa?

POR QUÉ EXISTE (24-08-2026). Una auditoría independiente de nueve dictámenes
encontró el defecto más caro del lote: el selector «EPS / Entidad Pagadora»
había quedado en POSITIVA de un caso anterior, el texto pegado decía
«EPS: PPL», y **el motor defendió a PPL citando el contrato de POSITIVA**
(0525/2017 + Otrosí 03, tarifa SOAT −15%). Un dictamen así no solo pierde la
glosa: le muestra a la EPS que el hospital cita contratos ajenos.

Le pasó dos veces en el mismo lote (GL-192 y GL-198). No es distracción del
auditor: el formulario conserva la EPS anterior y el texto se pega encima.

QUÉ SE HACE Y QUÉ NO. Solo se mira una declaración EXPLÍCITA al principio de
un renglón —«EPS: X», «ENTIDAD PAGADORA: X», «PAGADOR: X»—, que es como el
auditor rotula el caso. Una mención de paso («paciente remitido de COOSALUD»)
NO cuenta: bloquear por eso sería estorbar a quien narra bien el caso.

La comparación reusa el mismo comparador de EPS del buscador de tarifas, para
que «FAMISANAR» y «FAMISANAR EPS» no se vean como entidades distintas.
"""

from __future__ import annotations

import re
import unicodedata

# «EPS: PPL», «EPS/ENTIDAD PAGADORA: POSITIVA», «PAGADOR - COOSALUD».
# Debe ir al arranque de un renglón o después de un separador de campos,
# que es como quedan los rótulos cuando el auditor pega el caso.
_DECLARACION_EPS = re.compile(
    r"(?:^|[\n·|;])\s*"
    r"(?:EPS|ENTIDAD(?:\s+PAGADORA)?|PAGADOR(?:A)?|ERP|ASEGURADOR(?:A)?)"
    r"\s*[:\-–]\s*"
    r"([^\n·|;,.]{2,60})",
    re.IGNORECASE,
)

# Palabras que no son el nombre de una entidad aunque queden tras el rótulo.
_NO_ES_NOMBRE = {
    "N/A",
    "NA",
    "NO APLICA",
    "SIN DEFINIR",
    "PENDIENTE",
    "POR DEFINIR",
    "",
}


def _limpiar(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", (nombre or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).upper().strip(" .·-–")


def eps_declaradas_en_texto(texto: str) -> list[str]:
    """Los nombres de EPS que el texto rotula explícitamente."""
    if not texto:
        return []
    vistos: list[str] = []
    for m in _DECLARACION_EPS.finditer(texto):
        nombre = _limpiar(m.group(1))
        if nombre in _NO_ES_NOMBRE or len(nombre) < 2:
            continue
        if nombre not in vistos:
            vistos.append(nombre)
    return vistos


def _son_la_misma(a: str, b: str) -> bool:
    """Reusa el comparador del buscador de tarifas: «FAMISANAR» = «FAMISANAR EPS»."""
    a, b = _limpiar(a), _limpiar(b)
    if not a or not b:
        return True  # sin dato no se puede afirmar que difieran
    if a == b or a in b or b in a:
        return True
    try:
        from app.services.dictamen_stale import _matchea_eps

        return bool(_matchea_eps(a, b))
    except Exception:
        # Si el comparador no está disponible, NO se inventa un choque.
        return True


def choque_de_eps(eps_formulario: str, texto_glosa: str) -> str | None:
    """El nombre que el texto declara cuando NO es la EPS del formulario.

    Devuelve None cuando no hay conflicto — que es el caso normal.
    """
    declaradas = eps_declaradas_en_texto(texto_glosa)
    if not declaradas:
        return None
    for nombre in declaradas:
        if not _son_la_misma(eps_formulario, nombre):
            return nombre
    return None


def mensaje_de_choque(eps_formulario: str, eps_texto: str) -> str:
    """Lo que se le dice al auditor, en su idioma y con la salida a mano."""
    return (
        f"El selector de arriba dice «{_limpiar(eps_formulario)}» pero el texto de "
        f"la glosa dice «{_limpiar(eps_texto)}».\n\n"
        f"No se generó el dictamen a propósito: con el selector en la EPS "
        f"equivocada, el motor defiende citando el CONTRATO Y LAS TARIFAS DE OTRA "
        f"entidad, y eso se radica ante la EPS como un error del hospital.\n\n"
        f"Corrija el selector a «{_limpiar(eps_texto)}» y vuelva a analizar. Si de "
        f"verdad la pagadora es «{_limpiar(eps_formulario)}», quite del texto el "
        f"rótulo que dice lo contrario."
    )
