"""Del número de respuestas correctas al puntaje del ICFES.

Hay que separar dos cosas, porque una es exacta y la otra no:

1. **El puntaje global (0 a 500) es una fórmula oficial y exacta.** Si tú ya
   tienes los cinco puntajes por área, el global se calcula sin margen de
   error. Eso está en :func:`puntaje_global`.

2. **Pasar de "acerté 34 de 50" a un puntaje de área (0 a 100) es una
   estimación.** El ICFES no usa una regla de tres: usa un modelo estadístico
   (TRI) que pesa cada pregunta según su dificultad real, medida con miles de
   estudiantes. Nosotros no tenemos esos datos, así que este módulo entrega
   una **estimación orientativa** con una curva declarada y editable
   (:data:`CURVA_PUNTAJE`), nunca "el puntaje del ICFES".

Regla de la casa: cuando el sistema muestre un puntaje estimado, debe decir
que es estimado. :func:`describir_estimacion` existe justamente para eso.

Fuentes (consultadas el 2026-08-20):

- Fórmula del puntaje global (índice global × 5, pesos 3-3-3-3-1).
- Promedio nacional del puntaje global entre 250 y 260 puntos en los últimos
  años; por encima de 400 se considera excepcional.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dominio import AREAS, OPCIONES_POR_PREGUNTA, ORDEN_AREAS, Area

# ---------------------------------------------------------------------------
# 1. Puntaje global: fórmula oficial
# ---------------------------------------------------------------------------


def indice_global(puntajes: dict[Area, float]) -> float:
    """Promedio ponderado de las cinco áreas, en escala 0 a 100.

    Es el paso intermedio de la fórmula oficial::

        IG = (3·LC + 3·MAT + 3·SOC + 3·CN + 1·ING) / 13

    Faltar un área no se asume como cero: se exige que estén las cinco, porque
    un global calculado con áreas faltantes engaña.
    """
    faltantes = [a.nombre for a in ORDEN_AREAS if a not in puntajes]
    if faltantes:
        raise ValueError(f"Faltan puntajes de: {', '.join(faltantes)}")
    for area, valor in puntajes.items():
        if not 0 <= valor <= 100:
            raise ValueError(f"{area.nombre}: el puntaje de área va de 0 a 100, llegó {valor}")
    numerador = sum(puntajes[a] * AREAS[a].peso for a in ORDEN_AREAS)
    return numerador / sum(AREAS[a].peso for a in ORDEN_AREAS)


def puntaje_global(puntajes: dict[Area, float]) -> int:
    """El puntaje global del Saber 11, de 0 a 500 y sin decimales.

    Ejemplo:
        >>> from icfes.dominio import Area
        >>> puntaje_global({a: 80 for a in Area})
        400
    """
    return round(indice_global(puntajes) * 5)


def aporte_al_global(area: Area) -> float:
    """Cuántos puntos del global (0-500) gana subir **un punto** en esta área.

    Este número decide dónde vale la pena invertir el tiempo de estudio:

    - Lectura Crítica, Matemáticas, Sociales y Ciencias Naturales: 1,15 puntos.
    - Inglés: 0,38 puntos.

    Es decir, un punto en Matemáticas vale **tres veces** un punto en Inglés.
    No significa abandonar Inglés: significa que si te sobra una hora, casi
    siempre rinde más en las áreas de peso 3.
    """
    return AREAS[area].peso * 5 / sum(AREAS[a].peso for a in ORDEN_AREAS)


# ---------------------------------------------------------------------------
# 2. Puntaje por área: estimación declarada
# ---------------------------------------------------------------------------

#: Curva que traduce "proporción de respuestas correctas" a "puntaje de área".
#:
#: Cada par es (proporción acertada, puntaje estimado 0-100). Entre dos puntos
#: se interpola en línea recta. La curva es más generosa que una regla de tres
#: porque el examen real incluye preguntas muy difíciles que casi nadie
#: responde: acertar la mitad del examen NO es un puntaje de 50 sobre 100 malo,
#: es aproximadamente el promedio nacional.
#:
#: **Cómo calibrarla con tu propio resultado:** cuando presentes un simulacro
#: oficial del ICFES o tengas un resultado real, compara el porcentaje que
#: acertaste con el puntaje que te dieron y mueve el punto más cercano de esta
#: lista. El sistema entero queda calibrado a ti.
CURVA_PUNTAJE: tuple[tuple[float, float], ...] = (
    (0.00, 0.0),
    (0.25, 20.0),  # marcar todo al azar en preguntas de 4 opciones
    (0.40, 38.0),
    (0.50, 48.0),  # cerca del promedio nacional por área
    (0.60, 57.0),
    (0.70, 66.0),
    (0.80, 76.0),
    (0.90, 87.0),
    (1.00, 100.0),
)


def _interpolar(x: float, curva: tuple[tuple[float, float], ...]) -> float:
    """Busca ``x`` en la curva y devuelve el valor interpolado en línea recta."""
    if x <= curva[0][0]:
        return curva[0][1]
    if x >= curva[-1][0]:
        return curva[-1][1]
    for (x0, y0), (x1, y1) in zip(curva, curva[1:], strict=False):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return curva[-1][1]


def estimar_puntaje_area(correctas: int, total: int) -> int:
    """Estimación del puntaje de área (0 a 100) a partir de los aciertos.

    Args:
        correctas: cuántas respondiste bien.
        total: cuántas preguntas tenía la práctica o el simulacro.

    No es el puntaje del ICFES. Es una estimación con la curva declarada en
    :data:`CURVA_PUNTAJE`, útil para ver si vas subiendo o bajando.
    """
    if total <= 0:
        raise ValueError("No se puede estimar un puntaje sin preguntas")
    if not 0 <= correctas <= total:
        raise ValueError(f"Aciertos fuera de rango: {correctas} de {total}")
    return round(_interpolar(correctas / total, CURVA_PUNTAJE))


def proporcion_para_puntaje(puntaje: float) -> float:
    """El camino de vuelta: qué proporción hay que acertar para ese puntaje.

    Sirve para responder la pregunta que de verdad importa: *"si quiero 80 en
    Matemáticas, ¿cuántas de las 50 tengo que responder bien?"*.
    """
    if not 0 <= puntaje <= 100:
        raise ValueError("El puntaje de área va de 0 a 100")
    inversa = tuple((y, x) for x, y in CURVA_PUNTAJE)
    return _interpolar(puntaje, inversa)


def correctas_para_puntaje(puntaje: float, total: int) -> int:
    """Cuántas preguntas de ``total`` hay que acertar para llegar a ``puntaje``.

    Redondea hacia arriba: es preferible apuntarle a una de más que quedarse
    corto por medio punto.
    """
    if total <= 0:
        raise ValueError("Hacen falta preguntas para calcular la meta")
    exactas = proporcion_para_puntaje(puntaje) * total
    return min(total, -int(-exactas // 1))


def correccion_por_azar(correctas: int, total: int) -> float:
    """Proporción acertada quitando lo que se explica por pura suerte.

    En preguntas de cuatro opciones, marcar al azar acierta una de cada cuatro.
    Esta cuenta responde: *"de lo que acerté, ¿cuánto sabía de verdad?"*.
    Es un termómetro honesto para ver si estás aprendiendo o adivinando.
    """
    if total <= 0:
        raise ValueError("No se puede corregir por azar sin preguntas")
    azar = 1 / OPCIONES_POR_PREGUNTA
    proporcion = correctas / total
    return max(0.0, (proporcion - azar) / (1 - azar))


def describir_estimacion(correctas: int, total: int) -> str:
    """Una frase honesta para mostrar junto a cualquier puntaje estimado."""
    puntaje = estimar_puntaje_area(correctas, total)
    limpio = correccion_por_azar(correctas, total)
    return (
        f"{correctas} de {total} correctas → puntaje estimado {puntaje}/100 "
        f"(dominio real sin contar la suerte: {limpio * 100:.0f} %). "
        "Es una estimación del sistema, no el puntaje oficial del ICFES."
    )


# ---------------------------------------------------------------------------
# 3. Lectura de los resultados
# ---------------------------------------------------------------------------

#: Niveles de la prueba de Inglés, alineados al Marco Común Europeo (MCER).
#: El ICFES clasifica en Pre-A1, A1, A2 y B1. Los cortes que usa este sistema
#: son una **referencia orientativa** para entrenar, no la tabla oficial.
NIVELES_INGLES: tuple[tuple[int, str, str], ...] = (
    (47, "Pre-A1", "Aún no alcanza el nivel más básico del MCER."),
    (58, "A1", "Entiende palabras y frases sueltas muy sencillas."),
    (68, "A2", "Entiende textos cortos y conversaciones cotidianas."),
    (101, "B1", "Entiende textos largos y sostiene una conversación."),
)


def nivel_ingles(puntaje: float) -> tuple[str, str]:
    """Nivel MCER estimado a partir del puntaje de Inglés (0 a 100)."""
    if not 0 <= puntaje <= 100:
        raise ValueError("El puntaje de Inglés va de 0 a 100")
    for tope, nivel, descripcion in NIVELES_INGLES:
        if puntaje < tope:
            return nivel, descripcion
    return NIVELES_INGLES[-1][1], NIVELES_INGLES[-1][2]


@dataclass(frozen=True)
class Banda:
    """Cómo se lee un puntaje global."""

    nombre: str
    desde: int
    hasta: int
    significado: str


#: Lectura del puntaje global. El ancla con dato duro es el promedio nacional
#: (entre 250 y 260 en los últimos años) y el umbral de 400 como excepcional.
BANDAS_GLOBAL: tuple[Banda, ...] = (
    Banda("Bajo", 0, 200, "Muy por debajo del promedio nacional."),
    Banda("En construcción", 201, 250, "Justo por debajo del promedio nacional."),
    Banda("Promedio", 251, 300, "En el rango del promedio nacional (250 a 260)."),
    Banda("Bueno", 301, 350, "Por encima del promedio; abre buena parte de los programas."),
    Banda("Muy bueno", 351, 400, "Rango de becas parciales y programas de alta demanda."),
    Banda("Excepcional", 401, 500, "Rango de excelencia y becas completas."),
)


def banda_global(puntaje: int) -> Banda:
    """En qué banda cae un puntaje global (0 a 500)."""
    if not 0 <= puntaje <= 500:
        raise ValueError("El puntaje global va de 0 a 500")
    for banda in BANDAS_GLOBAL:
        if puntaje <= banda.hasta:
            return banda
    return BANDAS_GLOBAL[-1]


#: Semáforo por área que usa este sistema para decidir en qué enfocar el
#: estudio. No son los niveles oficiales del ICFES (esos están en los
#: documentos de "niveles de desempeño" de cada prueba); son los cortes
#: prácticos con los que el plan reparte las horas.
SEMAFORO_AREA: tuple[tuple[int, str, str], ...] = (
    (36, "crítico", "Hay vacíos de base. Toca volver a la teoría."),
    (51, "en construcción", "Ya hay base, falta práctica dirigida."),
    (71, "sólido", "Buen nivel. Ahora se pulen las preguntas difíciles."),
    (101, "alto", "Nivel alto. Se sostiene con repaso y simulacros."),
)


def semaforo_area(puntaje: float) -> tuple[str, str]:
    """Etiqueta práctica del nivel en un área, para repartir el estudio."""
    if not 0 <= puntaje <= 100:
        raise ValueError("El puntaje de área va de 0 a 100")
    for tope, etiqueta, consejo in SEMAFORO_AREA:
        if puntaje < tope:
            return etiqueta, consejo
    return SEMAFORO_AREA[-1][1], SEMAFORO_AREA[-1][2]


# ---------------------------------------------------------------------------
# 4. Metas: de un puntaje global deseado a metas por área
# ---------------------------------------------------------------------------


def meta_por_area(
    meta_global: int,
    actuales: dict[Area, float] | None = None,
) -> dict[Area, int]:
    """Reparte una meta global (0 a 500) en metas por área (0 a 100).

    Si no se pasan los puntajes actuales, reparte la meta pareja: todas las
    áreas al mismo nivel. Si se pasan, sube más las áreas donde ya hay ventaja
    (subir de 70 a 80 cuesta menos que subir de 30 a 80) sin dejar ninguna
    abandonada, y respeta el tope de 100.

    Ejemplo:
        >>> from icfes.dominio import Area
        >>> meta_por_area(400)[Area.MATEMATICAS]
        80
    """
    if not 0 <= meta_global <= 500:
        raise ValueError("La meta global va de 0 a 500")
    objetivo_ig = meta_global / 5
    if not actuales:
        return {a: round(objetivo_ig) for a in ORDEN_AREAS}

    faltantes = [a.nombre for a in ORDEN_AREAS if a not in actuales]
    if faltantes:
        raise ValueError(f"Faltan puntajes actuales de: {', '.join(faltantes)}")

    pesos = {a: AREAS[a].peso for a in ORDEN_AREAS}
    total_peso = sum(pesos.values())
    ig_actual = sum(actuales[a] * pesos[a] for a in ORDEN_AREAS) / total_peso
    subida_ig = objetivo_ig - ig_actual
    if subida_ig <= 0:
        return {a: round(min(100, actuales[a])) for a in ORDEN_AREAS}

    # Cada área recibe una subida proporcional al techo que le queda. Se itera
    # porque las áreas que topan en 100 devuelven su parte a las demás.
    metas = {a: float(actuales[a]) for a in ORDEN_AREAS}
    for _ in range(20):
        ig = sum(metas[a] * pesos[a] for a in ORDEN_AREAS) / total_peso
        falta = objetivo_ig - ig
        if falta <= 0.01:
            break
        margen = {a: max(0.0, 100.0 - metas[a]) for a in ORDEN_AREAS}
        capacidad = sum(margen[a] * pesos[a] for a in ORDEN_AREAS) / total_peso
        if capacidad <= 0:
            break
        factor = min(1.0, falta / capacidad)
        for a in ORDEN_AREAS:
            metas[a] = min(100.0, metas[a] + margen[a] * factor)
    return {a: round(metas[a]) for a in ORDEN_AREAS}


def brecha_hasta_meta(actuales: dict[Area, float], meta_global: int) -> dict[Area, float]:
    """Cuántos puntos le faltan a cada área para la meta global."""
    metas = meta_por_area(meta_global, actuales)
    return {a: max(0.0, metas[a] - actuales[a]) for a in ORDEN_AREAS}
