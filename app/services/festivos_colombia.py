"""El calendario colombiano completo, calculado — no copiado a mano.

POR QUÉ EXISTE (08-09-2026). El motor traía los festivos escritos a mano en
una lista (`FERIADOS_CO`, en `glosa_service.py`). Sirve mientras alguien la
mantenga, pero se acaba: hoy llega hasta 2028 y **2027 y 2028 están mal**
(ver `tests/test_services/test_festivos_colombia.py`, que lo demuestra con
el calendario en la mano). Y una cuenta de plazos con un festivo equivocado
manda una glosa limítrofe al lado que no era.

Los festivos de Colombia no son un dato que haya que buscar: son una
fórmula. Este módulo la aplica y sirve **cualquier año**, sin que nadie
tenga que volver a escribir una lista.

Las tres familias:

  · **Fijos** — caen el día que caen: 1 de enero, 1 de mayo, 20 de julio,
    7 de agosto, 8 y 25 de diciembre.
  · **Trasladados al lunes siguiente** (Ley 51 de 1983, la «Ley Emiliani»):
    Reyes, San José, San Pedro y San Pablo, la Asunción, el Día de la Raza,
    Todos los Santos y la Independencia de Cartagena. Si ya caen lunes, se
    quedan; si no, pasan al lunes SIGUIENTE — nunca al anterior. Ese fue
    justamente el error de la lista vieja.
  · **Movidos con la Pascua** — Jueves y Viernes Santo se quedan donde caen;
    la Ascensión, el Corpus Christi y el Sagrado Corazón se corren al lunes.

La Pascua se calcula con el método de Meeus/Butcher (calendario gregoriano),
el mismo de las tablas litúrgicas. La prueba lo verifica de dos maneras: que
todo domingo de Pascua caiga en domingo entre 2020 y 2100, y que los
festivos generados para 2025 y 2026 coincidan **uno a uno** con los que el
hospital ya venía usando y dio por buenos.

Este módulo no toca la red ni la base: fechas entran, fechas salen.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

# ── Fijos: (mes, día, nombre) ────────────────────────────────────────────
FIJOS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Año Nuevo"),
    (5, 1, "Día del Trabajo"),
    (7, 20, "Grito de Independencia"),
    (8, 7, "Batalla de Boyacá"),
    (12, 8, "Inmaculada Concepción"),
    (12, 25, "Navidad"),
)

# ── Trasladables al lunes siguiente (Ley 51 de 1983) ─────────────────────
EMILIANI: tuple[tuple[int, int, str], ...] = (
    (1, 6, "Reyes Magos"),
    (3, 19, "San José"),
    (6, 29, "San Pedro y San Pablo"),
    (8, 15, "Asunción de la Virgen"),
    (10, 12, "Día de la Raza"),
    (11, 1, "Todos los Santos"),
    (11, 11, "Independencia de Cartagena"),
)

# ── Los que dependen de la Pascua: (días desde el domingo, traslada, nombre)
# Jueves y Viernes Santo NO se trasladan: caen antes del domingo.
PASCUALES: tuple[tuple[int, bool, str], ...] = (
    (-3, False, "Jueves Santo"),
    (-2, False, "Viernes Santo"),
    (39, True, "Ascensión del Señor"),
    (60, True, "Corpus Christi"),
    (68, True, "Sagrado Corazón"),
)


def domingo_de_pascua(anio: int) -> date:
    """Domingo de Resurrección del año (Meeus/Butcher, gregoriano)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ele = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ele) // 451
    mes, dia = divmod(h + ele - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _lunes_siguiente(d: date) -> date:
    """El lunes de esa semana o el de la siguiente — nunca uno anterior."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=256)
def festivos_del_anio(anio: int) -> dict[date, str]:
    """Los festivos del año, con el nombre de cada uno."""
    if not 1984 <= anio <= 2200:
        # Antes de 1984 no regía la Ley 51 de 1983 y el calendario era otro.
        # Mejor negarse que devolver un calendario que no fue.
        raise ValueError(f"año fuera del rango aplicable de la Ley 51 de 1983: {anio}")

    salida: dict[date, str] = {}
    for mes, dia, nombre in FIJOS:
        salida[date(anio, mes, dia)] = nombre
    for mes, dia, nombre in EMILIANI:
        salida[_lunes_siguiente(date(anio, mes, dia))] = nombre

    pascua = domingo_de_pascua(anio)
    for desfase, traslada, nombre in PASCUALES:
        f = pascua + timedelta(days=desfase)
        salida[_lunes_siguiente(f) if traslada else f] = nombre
    return salida


def es_festivo(d: date) -> bool:
    return d in festivos_del_anio(d.year)


def es_habil(d: date) -> bool:
    """Hábil = de lunes a viernes y que no sea festivo."""
    return d.weekday() < 5 and not es_festivo(d)


def siguiente_habil(d: date) -> date:
    """El mismo día si es hábil; si no, el primer hábil que siga."""
    while not es_habil(d):
        d += timedelta(days=1)
    return d


def dias_habiles_entre(desde: date, hasta: date) -> int:
    """Días hábiles que hay ENTRE las dos fechas, sin contar el día inicial.

    Es el mismo criterio que ya usaba el motor para la extemporaneidad: se
    cuenta a partir del día siguiente. Si `hasta` es anterior a `desde`,
    devuelve 0 — un plazo no corre hacia atrás.
    """
    if hasta <= desde:
        return 0
    dias, curr = 0, desde
    while curr < hasta:
        curr += timedelta(days=1)
        if es_habil(curr):
            dias += 1
    return dias
