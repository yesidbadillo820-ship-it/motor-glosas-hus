"""Medir el avance de verdad: dominio, errores, racha y proyección.

Estudiar sin medir es estudiar a ciegas. Este módulo responde cuatro preguntas
que un estudiante necesita poder contestar en cualquier momento del año:

1. **¿Qué domino y qué no?** No por área (demasiado grueso) sino por
   competencia, que es como el ICFES pregunta.
2. **¿Por qué estoy fallando?** El cuaderno de errores agrupa por causa: no es
   lo mismo fallar por no saber el tema que por afán.
3. **¿Estoy siendo constante?** La racha de días seguidos.
4. **¿A dónde voy a llegar?** La proyección al día del examen, con la
   advertencia de qué tan confiable es.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from .dominio import AREAS, ORDEN_AREAS, Area, CausaError
from .fechas import cuenta_regresiva
from .puntaje import banda_global, semaforo_area

#: A los 30 días, un resultado pesa la mitad que uno de hoy. Así el dominio
#: refleja cómo estás AHORA y no cómo estabas en marzo.
VIDA_MEDIA_DIAS: float = 30.0

#: Con menos de este número de intentos, hablar de «dominio» es adivinar.
MINIMO_PARA_MEDIR: int = 4

#: Con menos de este número de simulacros, la proyección no es confiable.
MINIMO_PARA_PROYECTAR: int = 3


@dataclass(frozen=True)
class Intento:
    """Una pregunta respondida, con todo lo que hace falta para aprender de ella."""

    fecha: date
    pregunta_id: str
    area: Area
    competencia: str
    tema: str
    acerto: bool
    segundos: float | None = None
    causa: CausaError | None = None


def _peso_por_recencia(intento: Intento, hoy: date) -> float:
    """Cuánto pesa un intento hoy: lo viejo pesa menos."""
    dias = max(0, (hoy - intento.fecha).days)
    return 0.5 ** (dias / VIDA_MEDIA_DIAS)


@dataclass(frozen=True)
class Dominio:
    """Qué tan dominada está una competencia o un área."""

    nombre: str
    aciertos: int
    intentos: int
    proporcion: float
    medible: bool

    @property
    def porcentaje(self) -> float:
        return self.proporcion * 100

    @property
    def etiqueta(self) -> str:
        if not self.medible:
            return "sin datos suficientes"
        return semaforo_area(min(100.0, self.proporcion * 100))[0]


def _dominio(nombre: str, intentos: list[Intento], hoy: date) -> Dominio:
    if not intentos:
        return Dominio(nombre, 0, 0, 0.0, False)
    peso_total = sum(_peso_por_recencia(i, hoy) for i in intentos)
    peso_bueno = sum(_peso_por_recencia(i, hoy) for i in intentos if i.acerto)
    proporcion = peso_bueno / peso_total if peso_total else 0.0
    return Dominio(
        nombre=nombre,
        aciertos=sum(1 for i in intentos if i.acerto),
        intentos=len(intentos),
        proporcion=proporcion,
        medible=len(intentos) >= MINIMO_PARA_MEDIR,
    )


def dominio_por_area(intentos: list[Intento], hoy: date) -> dict[Area, Dominio]:
    """Nivel de dominio de cada área, dando más peso a lo reciente."""
    agrupados: dict[Area, list[Intento]] = defaultdict(list)
    for i in intentos:
        agrupados[i.area].append(i)
    return {a: _dominio(AREAS[a].nombre, agrupados.get(a, []), hoy) for a in ORDEN_AREAS}


def dominio_por_competencia(intentos: list[Intento], hoy: date) -> dict[str, Dominio]:
    """Nivel de dominio de cada competencia evaluada."""
    agrupados: dict[str, list[Intento]] = defaultdict(list)
    for i in intentos:
        agrupados[i.competencia].append(i)
    return {c: _dominio(c, lista, hoy) for c, lista in agrupados.items()}


def puntos_debiles(intentos: list[Intento], hoy: date, cuantos: int = 5) -> list[Dominio]:
    """Las competencias más flojas, que son por donde debe empezar el estudio."""
    medibles = [d for d in dominio_por_competencia(intentos, hoy).values() if d.medible]
    medibles.sort(key=lambda d: (d.proporcion, -d.intentos))
    return medibles[:cuantos]


def temas_a_reforzar(intentos: list[Intento], cuantos: int = 8) -> list[tuple[str, int, int]]:
    """Los temas con más fallas: (tema, fallas, intentos)."""
    conteo: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for i in intentos:
        conteo[i.tema][1] += 1
        if not i.acerto:
            conteo[i.tema][0] += 1
    ordenados = sorted(conteo.items(), key=lambda par: (-par[1][0], par[0]))
    return [(tema, fallas, total) for tema, (fallas, total) in ordenados[:cuantos] if fallas]


@dataclass(frozen=True)
class EntradaCuaderno:
    """Una causa de error, con cuántas veces pasó y cómo se corrige."""

    causa: CausaError
    veces: int
    porcentaje: float

    @property
    def descripcion(self) -> str:
        return self.causa.descripcion

    @property
    def remedio(self) -> str:
        return self.causa.remedio


def cuaderno_errores(intentos: list[Intento]) -> list[EntradaCuaderno]:
    """Por qué se está fallando, de la causa más frecuente a la menos.

    Es la herramienta más rentable de toda la preparación: si la mitad de los
    errores son por afán y no por desconocimiento, estudiar más temas no
    arregla nada. Hay que entrenar el reloj.
    """
    fallas = [i for i in intentos if not i.acerto and i.causa is not None]
    if not fallas:
        return []
    conteo = Counter(i.causa for i in fallas)
    total = sum(conteo.values())
    return [
        EntradaCuaderno(causa=causa, veces=veces, porcentaje=veces / total * 100)
        for causa, veces in conteo.most_common()
    ]


def reincidentes(intentos: list[Intento], minimo: int = 2) -> list[tuple[str, int]]:
    """Preguntas falladas más de una vez: son las que de verdad no se saben."""
    fallas = Counter(i.pregunta_id for i in intentos if not i.acerto)
    return [(pid, veces) for pid, veces in fallas.most_common() if veces >= minimo]


def racha(intentos: list[Intento], hoy: date) -> int:
    """Cuántos días seguidos se ha estudiado, contando hasta hoy o ayer.

    Se acepta que el último día sea ayer para no romper la racha de quien
    todavía no ha estudiado hoy: castigarlo a las 8 de la mañana desmotiva.
    """
    dias = {i.fecha for i in intentos}
    if not dias:
        return 0
    arranque = hoy if hoy in dias else hoy - timedelta(days=1)
    if arranque not in dias:
        return 0
    cuenta = 0
    actual = arranque
    while actual in dias:
        cuenta += 1
        actual -= timedelta(days=1)
    return cuenta


@dataclass(frozen=True)
class Proyeccion:
    """A dónde se va a llegar el día del examen, si el ritmo se sostiene."""

    puntaje_proyectado: int | None
    puntos_por_mes: float | None
    simulacros_usados: int
    confiable: bool
    mensaje: str


def proyectar(
    historial: list[tuple[date, int]],
    fecha_examen: date,
    meta_global: int | None = None,
) -> Proyeccion:
    """Proyecta el puntaje global del día del examen con una recta de tendencia.

    Args:
        historial: pares (fecha del simulacro, puntaje global estimado).
        fecha_examen: el día del examen.
        meta_global: la meta, para decir si el ritmo alcanza.

    La proyección es una recta de mínimos cuadrados sobre los simulacros. Con
    menos de tres puntos no se declara confiable, y así se dice: prometer un
    puntaje con dos datos es engañar.
    """
    puntos = sorted(historial)
    if len(puntos) < 2:
        return Proyeccion(
            puntaje_proyectado=puntos[0][1] if puntos else None,
            puntos_por_mes=None,
            simulacros_usados=len(puntos),
            confiable=False,
            mensaje=(
                "Con un solo simulacro no hay tendencia que proyectar. "
                "Haz al menos tres, separados por semanas."
            ),
        )

    origen = puntos[0][0]
    xs = [(f - origen).days for f, _ in puntos]
    ys = [float(p) for _, p in puntos]
    n = len(xs)
    media_x = sum(xs) / n
    media_y = sum(ys) / n
    varianza = sum((x - media_x) ** 2 for x in xs)
    if varianza == 0:
        return Proyeccion(
            puntaje_proyectado=round(media_y),
            puntos_por_mes=None,
            simulacros_usados=n,
            confiable=False,
            mensaje="Todos los simulacros son del mismo día: no hay tendencia en el tiempo.",
        )

    pendiente = sum((x - media_x) * (y - media_y) for x, y in zip(xs, ys, strict=True)) / varianza
    corte = media_y - pendiente * media_x
    dias_al_examen = (fecha_examen - origen).days
    proyectado = max(0, min(500, round(corte + pendiente * dias_al_examen)))
    por_mes = pendiente * 30
    confiable = n >= MINIMO_PARA_PROYECTAR

    if not confiable:
        mensaje = (
            f"Proyección con {n} simulacros: todavía no es confiable. "
            f"Haz al menos {MINIMO_PARA_PROYECTAR}."
        )
    elif pendiente <= 0:
        mensaje = (
            "El puntaje no está subiendo. Antes de estudiar más horas, "
            "revisa el cuaderno de errores: casi siempre el problema es el método."
        )
    elif meta_global is not None and proyectado < meta_global:
        falta = meta_global - proyectado
        mensaje = (
            f"Vas subiendo {por_mes:.0f} puntos al mes. A ese ritmo llegas a "
            f"{proyectado} y te faltarían {falta} para la meta de {meta_global}. "
            "Hay que apretar donde más pesa."
        )
    else:
        mensaje = f"Vas subiendo {por_mes:.0f} puntos al mes. A ese ritmo alcanzas la meta."

    return Proyeccion(
        puntaje_proyectado=proyectado,
        puntos_por_mes=por_mes,
        simulacros_usados=n,
        confiable=confiable,
        mensaje=mensaje,
    )


def informe(
    intentos: list[Intento],
    historial: list[tuple[date, int]],
    hoy: date,
    fecha_examen: date,
    meta_global: int,
) -> str:
    """El informe de progreso completo, en texto."""
    lineas = [
        "INFORME DE PROGRESO",
        f"{cuenta_regresiva(hoy, fecha_examen)}   ·   Meta: {meta_global} puntos",
        "",
    ]

    dias_seguidos = racha(intentos, hoy)
    lineas.append(
        f"Racha: {dias_seguidos} día{'s' if dias_seguidos != 1 else ''} seguidos estudiando."
        if dias_seguidos
        else "Racha: 0. Hoy es buen día para volver a empezar."
    )
    lineas.append(f"Preguntas respondidas en total: {len(intentos)}.")

    if historial:
        ultimo = max(historial)
        banda = banda_global(ultimo[1])
        lineas += [
            "",
            f"Último simulacro ({ultimo[0]:%d/%m/%Y}): {ultimo[1]} puntos — {banda.nombre}.",
            f"  {banda.significado}",
        ]
        p = proyectar(historial, fecha_examen, meta_global)
        if p.puntaje_proyectado is not None:
            lineas.append(f"Proyección al día del examen: {p.puntaje_proyectado} puntos.")
        lineas.append(f"  {p.mensaje}")

    if intentos:
        lineas += ["", "DOMINIO POR ÁREA (lo reciente pesa más)"]
        for area, d in dominio_por_area(intentos, hoy).items():
            if d.intentos == 0:
                lineas.append(f"  {AREAS[area].nombre:<24} sin practicar todavía")
            else:
                lineas.append(
                    f"  {AREAS[area].nombre:<24}{d.porcentaje:>5.0f}% "
                    f"({d.aciertos}/{d.intentos})  {d.etiqueta}"
                )

        flojas = puntos_debiles(intentos, hoy)
        if flojas:
            lineas += ["", "COMPETENCIAS MÁS FLOJAS"]
            lineas += [
                f"  · {d.nombre} — {d.porcentaje:.0f}% ({d.intentos} preguntas)" for d in flojas
            ]

        cuaderno = cuaderno_errores(intentos)
        if cuaderno:
            lineas += ["", "POR QUÉ ESTOY FALLANDO"]
            for entrada in cuaderno:
                lineas.append(
                    f"  · {entrada.descripcion} — {entrada.veces} veces "
                    f"({entrada.porcentaje:.0f}% de los errores)"
                )
                lineas.append(f"      Qué hacer: {entrada.remedio}")

        repetidas = reincidentes(intentos)
        if repetidas:
            ids = ", ".join(f"{pid} (×{veces})" for pid, veces in repetidas[:8])
            lineas += ["", f"PREGUNTAS FALLADAS MÁS DE UNA VEZ: {ids}"]

    return "\n".join(lineas)
