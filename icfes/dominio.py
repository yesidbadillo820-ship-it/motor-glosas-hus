"""Cómo es de verdad el examen Saber 11 del ICFES.

Todo lo que el resto del sistema necesita saber del examen está aquí y en un
solo lugar: las cinco áreas, cuánto pesa cada una, cuántas preguntas trae,
cómo se reparten entre las dos sesiones y qué competencias evalúa cada una.

Fuentes (consultadas el 2026-08-20):

- Guía de orientación del Examen Saber 11.º 2026-1, ICFES.
  https://www.icfes.gov.co/evaluaciones-icfes/saber-11/guia-de-orientacion-examen-saber-11/
- Niveles de desempeño de la prueba de Inglés, Saber 11.º, ICFES (2025).

Si el ICFES cambia la estructura, se cambia **este** archivo y todo el sistema
queda actualizado: no hay números del examen regados por el código.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

# ---------------------------------------------------------------------------
# Áreas del examen
# ---------------------------------------------------------------------------


class Area(StrEnum):
    """Las cinco pruebas que dan puntaje en el Saber 11."""

    LECTURA_CRITICA = "lectura_critica"
    MATEMATICAS = "matematicas"
    SOCIALES_CIUDADANAS = "sociales_ciudadanas"
    CIENCIAS_NATURALES = "ciencias_naturales"
    INGLES = "ingles"

    @property
    def ficha(self) -> FichaArea:
        """Los datos oficiales del área."""
        return AREAS[self]

    @property
    def nombre(self) -> str:
        """El nombre como aparece en el reporte del ICFES."""
        return AREAS[self].nombre


@dataclass(frozen=True)
class FichaArea:
    """Los datos oficiales de un área del examen.

    Atributos:
        area: la identificación del área.
        nombre: el nombre como aparece en el reporte de resultados.
        peso: cuánto pesa en el puntaje global (3 para todas menos Inglés).
        preguntas: cuántas preguntas calificables trae el examen real.
        preguntas_sesion_1: cuántas de esas se responden en la primera sesión.
        preguntas_sesion_2: cuántas en la segunda.
        competencias: lo que el ICFES mide en el área (no son "temas").
        componentes: los grandes bloques de contenido del área.
    """

    area: Area
    nombre: str
    peso: int
    preguntas: int
    preguntas_sesion_1: int
    preguntas_sesion_2: int
    competencias: tuple[str, ...]
    componentes: tuple[str, ...]

    def __post_init__(self) -> None:
        repartidas = self.preguntas_sesion_1 + self.preguntas_sesion_2
        if repartidas != self.preguntas:
            raise ValueError(
                f"{self.nombre}: las sesiones suman {repartidas} preguntas "
                f"pero el área tiene {self.preguntas}"
            )


AREAS: dict[Area, FichaArea] = {
    Area.LECTURA_CRITICA: FichaArea(
        area=Area.LECTURA_CRITICA,
        nombre="Lectura Crítica",
        peso=3,
        preguntas=41,
        # Lectura Crítica se responde completa en la primera sesión.
        preguntas_sesion_1=41,
        preguntas_sesion_2=0,
        competencias=(
            "Identificar y entender los contenidos explícitos del texto",
            "Comprender cómo se articulan las partes del texto",
            "Reflexionar y evaluar el contenido del texto",
        ),
        componentes=(
            "Texto continuo literario",
            "Texto continuo informativo",
            "Texto continuo filosófico",
            "Texto discontinuo",
        ),
    ),
    Area.MATEMATICAS: FichaArea(
        area=Area.MATEMATICAS,
        nombre="Matemáticas",
        peso=3,
        preguntas=50,
        preguntas_sesion_1=25,
        preguntas_sesion_2=25,
        competencias=(
            "Interpretación y representación",
            "Formulación y ejecución",
            "Argumentación",
        ),
        componentes=(
            "Numérico-variacional",
            "Geométrico-métrico",
            "Aleatorio",
        ),
    ),
    Area.SOCIALES_CIUDADANAS: FichaArea(
        area=Area.SOCIALES_CIUDADANAS,
        nombre="Sociales y Ciudadanas",
        peso=3,
        preguntas=50,
        preguntas_sesion_1=25,
        preguntas_sesion_2=25,
        competencias=(
            "Pensamiento social",
            "Interpretación y análisis de perspectivas",
            "Pensamiento reflexivo y sistémico",
        ),
        componentes=(
            "Constitución Política y derechos",
            "El espacio, el territorio, el ambiente y la población",
            "El poder, la economía y las organizaciones sociales",
            "El tiempo y las culturas",
        ),
    ),
    Area.CIENCIAS_NATURALES: FichaArea(
        area=Area.CIENCIAS_NATURALES,
        nombre="Ciencias Naturales",
        peso=3,
        preguntas=58,
        preguntas_sesion_1=29,
        preguntas_sesion_2=29,
        competencias=(
            "Uso comprensivo del conocimiento científico",
            "Explicación de fenómenos",
            "Indagación",
        ),
        componentes=(
            "Biológico",
            "Físico",
            "Químico",
            "Ciencia, tecnología y sociedad",
        ),
    ),
    Area.INGLES: FichaArea(
        area=Area.INGLES,
        nombre="Inglés",
        peso=1,
        preguntas=55,
        # Inglés se responde completo en la segunda sesión.
        preguntas_sesion_1=0,
        preguntas_sesion_2=55,
        competencias=(
            "Comprensión de textos cortos y avisos",
            "Comprensión de conversaciones",
            "Comprensión de textos largos",
            "Uso del idioma en contexto",
        ),
        componentes=(
            "Avisos y frases cotidianas",
            "Diálogos cortos",
            "Conversación",
            "Vocabulario en contexto",
            "Texto informativo",
            "Gramática en contexto",
        ),
    ),
}

#: Orden en que se muestran las áreas en pantalla y en los informes.
ORDEN_AREAS: tuple[Area, ...] = (
    Area.LECTURA_CRITICA,
    Area.MATEMATICAS,
    Area.SOCIALES_CIUDADANAS,
    Area.CIENCIAS_NATURALES,
    Area.INGLES,
)

#: Preguntas calificables del examen completo (41 + 50 + 50 + 58 + 55).
TOTAL_PREGUNTAS_CALIFICABLES: int = sum(f.preguntas for f in AREAS.values())

#: El cuadernillo real trae además preguntas de pilotaje que NO dan puntaje.
#: El ICFES las usa para calibrar preguntas de exámenes futuros.
PREGUNTAS_NO_CALIFICABLES: int = 24

#: Cada sesión del examen dura 4 horas y 30 minutos.
MINUTOS_POR_SESION: int = 270

#: Todas las preguntas del Saber 11 tienen cuatro opciones (A, B, C, D).
OPCIONES_POR_PREGUNTA: int = 4

#: Letras con que se numeran las opciones en el cuadernillo.
LETRAS_OPCIONES: tuple[str, ...] = ("A", "B", "C", "D")

#: Suma de los pesos: 3+3+3+3+1. El puntaje global divide entre este número.
SUMA_PESOS: int = sum(f.peso for f in AREAS.values())


def preguntas_de_sesion(sesion: int) -> dict[Area, int]:
    """Cuántas preguntas de cada área trae la sesión indicada (1 o 2).

    Ejemplo:
        >>> preguntas_de_sesion(1)[Area.LECTURA_CRITICA]
        41
    """
    if sesion not in (1, 2):
        raise ValueError("El examen solo tiene sesión 1 y sesión 2")
    campo = "preguntas_sesion_1" if sesion == 1 else "preguntas_sesion_2"
    return {area: getattr(ficha, campo) for area, ficha in AREAS.items() if getattr(ficha, campo)}


def segundos_por_pregunta(sesion: int) -> float:
    """Cuántos segundos hay, en promedio, para cada pregunta de la sesión.

    Este es el dato más útil del examen: si te demoras más de esto de forma
    sostenida, no alcanzas a terminar. La cuenta usa solo las preguntas
    calificables, así que el tiempo real por pregunta es todavía un poco menor.
    """
    total = sum(preguntas_de_sesion(sesion).values())
    return MINUTOS_POR_SESION * 60 / total


# ---------------------------------------------------------------------------
# Preguntas
# ---------------------------------------------------------------------------


class Dificultad(int, Enum):
    """Qué tan difícil es una pregunta, en cinco escalones."""

    MUY_FACIL = 1
    FACIL = 2
    MEDIA = 3
    DIFICIL = 4
    MUY_DIFICIL = 5

    @property
    def etiqueta(self) -> str:
        return {
            1: "muy fácil",
            2: "fácil",
            3: "media",
            4: "difícil",
            5: "muy difícil",
        }[self.value]


@dataclass(frozen=True)
class Pregunta:
    """Una pregunta de práctica con todo lo necesario para aprender de ella.

    Lo importante no es la pregunta: es la ``explicacion`` y la ``trampa``.
    Una pregunta sin explicación no enseña nada; solo mide.
    """

    id: str
    area: Area
    competencia: str
    componente: str
    tema: str
    dificultad: Dificultad
    enunciado: str
    opciones: tuple[str, ...]
    correcta: int
    explicacion: str
    trampa: str
    contexto: str = ""

    def __post_init__(self) -> None:
        if len(self.opciones) != OPCIONES_POR_PREGUNTA:
            raise ValueError(f"{self.id}: toda pregunta debe tener 4 opciones")
        if not 0 <= self.correcta < OPCIONES_POR_PREGUNTA:
            raise ValueError(f"{self.id}: la opción correcta debe ir de 0 a 3")
        if self.competencia not in self.area.ficha.competencias:
            raise ValueError(
                f"{self.id}: la competencia «{self.competencia}» no existe en {self.area.nombre}"
            )
        if self.componente not in self.area.ficha.componentes:
            raise ValueError(
                f"{self.id}: el componente «{self.componente}» no existe en {self.area.nombre}"
            )
        if not self.explicacion.strip():
            raise ValueError(f"{self.id}: una pregunta sin explicación no sirve para estudiar")

    @property
    def letra_correcta(self) -> str:
        """La letra (A-D) de la respuesta correcta."""
        return LETRAS_OPCIONES[self.correcta]

    def es_correcta(self, respuesta: int) -> bool:
        """¿La opción marcada es la correcta?"""
        return respuesta == self.correcta


class CausaError(StrEnum):
    """Por qué se falló una pregunta. Es el corazón del cuaderno de errores.

    Saber *que* fallaste no sirve. Sirve saber *por qué*: cada causa se
    corrige de una forma distinta.
    """

    CONCEPTO = "concepto"
    LECTURA = "lectura"
    CALCULO = "calculo"
    TIEMPO = "tiempo"
    DESCUIDO = "descuido"
    ADIVINE = "adivine"

    @property
    def descripcion(self) -> str:
        return {
            "concepto": "No sabía el tema. Toca volver a estudiarlo.",
            "lectura": "Entendí mal lo que preguntaban o el texto.",
            "calculo": "Sabía el tema pero me equivoqué en la operación.",
            "tiempo": "Me quedé sin tiempo y respondí de afán.",
            "descuido": "Sabía la respuesta y marqué otra opción.",
            "adivine": "No tenía idea y marqué al azar.",
        }[self.value]

    @property
    def remedio(self) -> str:
        return {
            "concepto": "Estudiar el tema de cero y volver a practicarlo en 2 días.",
            "lectura": "Subrayar qué piden antes de mirar las opciones.",
            "calculo": "Hacer la operación en el papel, no de memoria.",
            "tiempo": "Practicar con cronómetro y saltar lo que se atasque.",
            "descuido": "Revisar que la letra marcada sea la que se pensó.",
            "adivine": "Es un vacío de tema: mandarlo directo al plan de estudio.",
        }[self.value]
