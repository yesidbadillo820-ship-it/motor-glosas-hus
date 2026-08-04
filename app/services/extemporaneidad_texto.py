"""Detección de extemporaneidad desde el TEXTO de la glosa (Ronda 32).

Caso 3 de las pruebas del 22-jul-2026: la glosa traía las fechas en el
texto (factura del 02/04/2026, glosa radicada el 28/05/2026 ≈ 38 días
hábiles) pero los campos F. Radicación / F. Recepción del formulario
venían vacíos → el motor mostró "Fechas no ingresadas" y el dictamen
perdió el argumento ganador (aceptación tácita, Art. 57 Ley 1438/2011).

Este módulo lee SOLO fechas ETIQUETADAS (pegadas a "radicación de la
factura", "glosa notificada el", etc.) — nunca fechas sueltas — y calcula
los días hábiles entre ellas. La señal es INFERIDA, no confirmada: el
llamador la muestra como "POSIBLE extemporaneidad — verificar fechas" y
agrega el argumento como sección ADICIONAL, sin reemplazar la defensa de
fondo (el reemplazo total sigue reservado a fechas confirmadas en el
formulario, como siempre).

  detectar_extemporaneidad_en_texto(texto) -> dict | None
"""

from __future__ import annotations

import re
from datetime import date, timedelta

DIAS_HABILES_LIMITE = 20  # Art. 57 Ley 1438/2011 (formulación de la glosa)

# Sub-patrón de fecha: dd/mm/yyyy · yyyy-mm-dd · "28 DE MAYO DE 2026".
_PAT_FECHA = (
    r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4})"
)

_MESES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

# INICIO del plazo. Orden = prioridad: la RADICACIÓN de la factura ante la
# EPS es la que arranca el reloj del Art. 57; la fecha de emisión/expedición
# es un fallback que SOBREESTIMA los días transcurridos — otra razón por la
# que el resultado siempre se presenta como "verificar", nunca como hecho.
# Token opcional "N° HUS0000224871" / "HUS0000224871" / "224871" — permite
# que entre la etiqueta y la fecha esté el número del documento sin que la
# ventana [^0-9.] (que evita cruzar números ajenos) bloquee el match.
# Revisión adversarial 22-jul: el token EXIGE dígitos — la versión anterior
# (`N[°ºO\.]{0,2}\s*[A-Z0-9\-]+`) aceptaba "NO CORRESPONDE" como si fuera un
# número de documento y de ahí salía una extemporaneidad inventada con la
# fecha del PERIODO del contrato. Y sin la variante "pelada" (sin N°) el
# formato más común ("FACTURA 224871 RADICADA EL...") no se detectaba nunca.
_NUM_DOC = (
    r"(?:\s+(?:N[°º\.]{1,2}\s*|N[ÚU]MERO\s+|NRO\.?\s+|NO\.?\s+)?(?:[A-Z]{1,5}-?)?\d[\d\-]{3,})?"
)

# Las ventanas usan [^0-9.] — sin dígitos NI punto: una fecha no se busca
# cruzando el final de la oración (revisión adversarial 22-jul: la ventana
# ancha atribuía a la glosa fechas de otras cláusulas).
_PATRONES_INICIO: tuple[tuple[str, re.Pattern], ...] = (
    (
        "radicación de la factura",
        re.compile(r"RADICACI[ÓO]N\s+DE\s+LA\s+FACTURA" + _NUM_DOC + r"[^0-9.]{0,30}" + _PAT_FECHA),
    ),
    (
        "factura radicada el",
        re.compile(
            r"FACTURA" + _NUM_DOC + r"(?:(?!GLOSA)[^0-9.]){0,40}RADICADA\s+EL\s+" + _PAT_FECHA
        ),
    ),
    (
        "presentación de la factura",
        re.compile(
            r"PRESENTACI[ÓO]N\s+DE\s+LA\s+FACTURA" + _NUM_DOC + r"[^0-9.]{0,30}" + _PAT_FECHA
        ),
    ),
    (
        "fecha de la factura",
        re.compile(
            r"FECHA\s+DE\s+(?:LA\s+)?FACTURA(?:CI[ÓO]N)?" + _NUM_DOC + r"[^0-9.]{0,20}" + _PAT_FECHA
        ),
    ),
    (
        "factura del",
        re.compile(
            r"FACTURA(?:\s+ELECTR[ÓO]NICA)?(?:\s+DE\s+VENTA)?"
            + _NUM_DOC
            + r"\s+DEL?\s+"
            + _PAT_FECHA
        ),
    ),
    (
        "factura emitida/expedida el",
        re.compile(
            r"FACTURA" + _NUM_DOC + r"[^0-9.]{0,40}(?:EMITIDA|EXPEDIDA)\s+EL\s+" + _PAT_FECHA
        ),
    ),
)

# FIN del plazo: la fecha en que la EPS formuló/notificó/radicó la GLOSA.
# El patrón 3 lleva tres blindajes (revisión adversarial 22-jul):
#   (?<!SE ) — "SE GLOSA PORQUE LA INCAPACIDAD FUE NOTIFICADA EL..." usa
#              GLOSA como VERBO y la fecha es de otra cosa;
#   \b       — que "GLOSADA/GLOSADO" no matchee como sustantivo;
#   (?!FACTURA) en la ventana — "GLOSA A LA FACTURA ... RADICADA EL" habla
#              de la radicación de la FACTURA, no de la glosa.
_PATRONES_GLOSA: tuple[tuple[str, re.Pattern], ...] = (
    (
        "radicación de la glosa",
        re.compile(
            r"RADICACI[ÓO]N\s+DE\s+LA\s+(?:GLOSA|OBJECI[ÓO]N)\b"
            + _NUM_DOC
            + r"[^0-9.]{0,30}"
            + _PAT_FECHA
        ),
    ),
    (
        "notificación de la glosa",
        re.compile(
            r"NOTIFICACI[ÓO]N\s+DE\s+LA\s+(?:GLOSA|OBJECI[ÓO]N)\b"
            + _NUM_DOC
            + r"[^0-9.]{0,30}"
            + _PAT_FECHA
        ),
    ),
    (
        "glosa radicada/notificada el",
        re.compile(
            r"(?<!SE )(?:GLOSA|OBJECI[ÓO]N)\b" + _NUM_DOC + r"(?:(?!FACTURA)[^0-9.]){0,60}"
            r"(?:RADICADA|NOTIFICADA|COMUNICADA|FORMULADA|INTERPUESTA)\s+EL\s+" + _PAT_FECHA
        ),
    ),
    (
        "fecha de la glosa",
        re.compile(
            r"FECHA\s+DE\s+(?:LA\s+)?(?:GLOSA|OBJECI[ÓO]N)\b"
            + _NUM_DOC
            + r"[^0-9.]{0,20}"
            + _PAT_FECHA
        ),
    ),
)


def _parse_fecha(s: str) -> date | None:
    """Parsea el texto capturado a date; None si no es una fecha sana."""
    s = " ".join((s or "").upper().split())
    d = m = a = 0
    mm = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if mm:
        d, m, a = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
    else:
        mm = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
        if mm:
            a, m, d = int(mm.group(1)), int(mm.group(2)), int(mm.group(3))
        else:
            mm = re.match(r"^(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚ]+)\s+DE\s+(\d{4})$", s)
            if mm:
                d, a = int(mm.group(1)), int(mm.group(3))
                m = _MESES.get(mm.group(2), 0)
    if not (2020 <= a <= 2035 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    try:
        return date(a, m, d)
    except ValueError:
        return None


def _buscar(texto: str, patrones) -> tuple[date, str] | None:
    """Primer patrón (en orden de prioridad) con fecha parseable."""
    for etiqueta, pat in patrones:
        for m in pat.finditer(texto):
            f = _parse_fecha(m.group(1))
            if f is not None:
                return f, etiqueta
    return None


def _cargar_feriados() -> list[str]:
    """Feriados colombianos "YYYY-MM-DD" (lista compartida del motor)."""
    try:
        from app.services.glosa_service import FERIADOS_CO

        return list(FERIADOS_CO)
    except Exception:
        return []


def _dias_habiles(desde: date, hasta: date, feriados: list[str]) -> int:
    """Días hábiles lun-vie excluyendo los feriados dados."""
    dias, curr = 0, desde
    while curr < hasta:
        curr += timedelta(days=1)
        if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in feriados:
            dias += 1
    return dias


def detectar_extemporaneidad_en_texto(texto: str) -> dict | None:
    """Busca fechas etiquetadas de factura y de glosa en el texto.

    Devuelve None si no hay AMBAS fechas etiquetadas o si son incoherentes
    (glosa anterior a la factura, o más de un año de diferencia — mejor no
    opinar que opinar mal). Si las hay:

      {
        "fecha_inicio": "2026-04-02",   # radicación/emisión de la factura
        "fecha_glosa": "2026-05-28",    # formulación/notificación de la glosa
        "etiqueta_inicio": str,          # qué etiqueta se usó (trazabilidad)
        "etiqueta_glosa": str,
        "dias_habiles": int,
        "es_extemporanea": bool,         # dias_habiles > 20
      }
    """
    if not (texto or "").strip():
        return None
    t = " ".join(str(texto).upper().split())

    inicio = _buscar(t, _PATRONES_INICIO)
    fin = _buscar(t, _PATRONES_GLOSA)
    if not inicio or not fin:
        return None
    f_ini, et_ini = inicio
    f_glo, et_glo = fin
    if f_glo <= f_ini or (f_glo - f_ini).days > 365:
        return None

    # Sin feriados cargados para los años implicados, el conteo trata los
    # festivos como hábiles y puede inflar una glosa limítrofe (19-20 días
    # reales) hasta "extemporánea". Mejor no opinar (revisión 22-jul).
    feriados = _cargar_feriados()
    anos_cubiertos = {f[:4] for f in feriados}
    if {str(f_ini.year), str(f_glo.year)} - anos_cubiertos:
        return None

    dias = _dias_habiles(f_ini, f_glo, feriados)
    return {
        "fecha_inicio": f_ini.isoformat(),
        "fecha_glosa": f_glo.isoformat(),
        "etiqueta_inicio": et_ini,
        "etiqueta_glosa": et_glo,
        "dias_habiles": dias,
        "es_extemporanea": dias > DIAS_HABILES_LIMITE,
    }
