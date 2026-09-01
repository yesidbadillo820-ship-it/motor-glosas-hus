"""Las piezas fijas del curso: niveles, temas, géneros y tipos de ejercicio.

Todo lo que el resto del paquete necesita saber sobre "cómo es el noruego" y
"cómo está organizado el curso" vive aquí, en un solo lugar.

Sobre la variante: el curso enseña **bokmål**, que es la forma escrita que usa
la gran mayoría de los noruegos y la única que se evalúa en la Norskprøven para
extranjeros. El nynorsk no se cubre.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum


class Nivel(StrEnum):
    """Niveles del Marco Común Europeo de Referencia (MCER)."""

    CERO = "cero"
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

    @property
    def orden(self) -> int:
        return list(Nivel).index(self)

    @property
    def titulo(self) -> str:
        return {
            "cero": "Desde cero",
            "A1": "A1 · Primeros pasos",
            "A2": "A2 · Básico",
            "B1": "B1 · Independiente",
            "B2": "B2 · Avanzado",
            "C1": "C1 · Dominio",
            "C2": "C2 · Maestría",
        }[self.value]

    @property
    def descripcion(self) -> str:
        return {
            "cero": "Nunca has visto noruego. Sonidos, saludos y las primeras frases.",
            "A1": "Te presentas, pides cosas sencillas y entiendes frases del día a día.",
            "A2": "Manejas situaciones cotidianas: compras, citas, familia, trabajo simple.",
            "B1": "Te defiendes solo. Es el nivel que pide la ciudadanía noruega.",
            "B2": "Discutes temas complejos. Es el nivel que piden muchas universidades y empleos.",
            "C1": "Usas el idioma con soltura en lo académico y lo profesional.",
            "C2": "Precisión y matiz cercanos a los de un hablante nativo.",
        }[self.value]


class Genero(StrEnum):
    """Los tres géneros del sustantivo noruego.

    En bokmål, casi todos los femeninos pueden usarse también como masculinos
    («ei jente» o «en jente»), y esa es la forma más común en Oslo y en los
    libros de texto. El curso enseña la forma en «en» y muestra la femenina.
    """

    MASCULINO = "en"
    FEMENINO = "ei"
    NEUTRO = "et"

    @property
    def articulo(self) -> str:
        return self.value

    @property
    def nombre_es(self) -> str:
        return {"en": "masculino", "ei": "femenino", "et": "neutro"}[self.value]


class GrupoVerbal(StrEnum):
    """Los cuatro grupos regulares del verbo noruego, más los irregulares.

    El pretérito se forma distinto según el grupo. Es lo primero que hay que
    saber para no equivocarse al hablar del pasado.
    """

    UNO = "1"
    DOS = "2"
    TRES = "3"
    CUATRO = "4"
    IRREGULAR = "irr"
    MODAL = "modal"

    @property
    def terminacion(self) -> str:
        return {
            "1": "-et (o -a)",
            "2": "-te",
            "3": "-de",
            "4": "-dde",
            "irr": "sin regla fija",
            "modal": "verbo modal",
        }[self.value]

    @property
    def explicacion(self) -> str:
        return {
            "1": "Raíz + -et. Ejemplo: snakke → snakket. También se acepta -a (snakka).",
            "2": "Raíz + -te. Ejemplo: spise → spiste.",
            "3": "Raíz + -de. Ejemplo: prøve → prøvde.",
            "4": "Verbos de una sílaba que terminan en vocal + -dde. Ejemplo: bo → bodde.",
            "irr": "Hay que aprenderlos de memoria. Ejemplo: gå → gikk.",
            "modal": "Acompañan a otro verbo en infinitivo SIN «å». Ejemplo: Jeg kan snakke.",
        }[self.value]


class TipoEjercicio(StrEnum):
    """Los tipos de ejercicio que el motor sabe generar y calificar."""

    OPCION = "opcion"
    TRADUCIR_ES_NO = "traducir_es_no"
    TRADUCIR_NO_ES = "traducir_no_es"
    ORDENAR = "ordenar"
    COMPLETAR = "completar"
    ESCUCHAR_OPCION = "escuchar_opcion"
    ESCUCHAR_ESCRIBIR = "escuchar_escribir"
    PAREJAS = "parejas"
    CONJUGAR = "conjugar"
    GENERO = "genero"
    FORMA_NOMINAL = "forma_nominal"
    ERROR = "error"
    DIALOGO = "dialogo"
    LECTURA = "lectura"
    PRONUNCIAR = "pronunciar"

    @property
    def etiqueta(self) -> str:
        return {
            "opcion": "Elige la respuesta",
            "traducir_es_no": "Traduce al noruego",
            "traducir_no_es": "Traduce al español",
            "ordenar": "Ordena las palabras",
            "completar": "Completa la frase",
            "escuchar_opcion": "Escucha y elige",
            "escuchar_escribir": "Escucha y escribe",
            "parejas": "Une las parejas",
            "conjugar": "Conjuga el verbo",
            "genero": "¿Qué género tiene?",
            "forma_nominal": "Forma del sustantivo",
            "error": "Encuentra el error",
            "dialogo": "Completa la conversación",
            "lectura": "Comprensión de lectura",
            "pronunciar": "Pronunciación",
        }[self.value]

    @property
    def usa_audio(self) -> bool:
        return self in (
            TipoEjercicio.ESCUCHAR_OPCION,
            TipoEjercicio.ESCUCHAR_ESCRIBIR,
            TipoEjercicio.PRONUNCIAR,
        )


@dataclass(frozen=True)
class Tema:
    """Un tema de vocabulario: agrupa palabras y frases del mismo campo."""

    clave: str
    nombre: str
    icono: str


#: Los temas del curso, en el orden en que se presentan.
TEMAS: tuple[Tema, ...] = (
    Tema("sonidos", "Sonidos y letras", "🔤"),
    Tema("saludos", "Saludos y cortesía", "👋"),
    Tema("personas", "Personas y pronombres", "🧑"),
    Tema("familia", "Familia", "👨‍👩‍👧"),
    Tema("numeros", "Números", "🔢"),
    Tema("tiempo", "Tiempo y fechas", "🕐"),
    Tema("comida", "Comida y bebida", "🍞"),
    Tema("casa", "La casa", "🏠"),
    Tema("ciudad", "Ciudad y transporte", "🚌"),
    Tema("compras", "Compras y dinero", "🛒"),
    Tema("trabajo", "Trabajo", "💼"),
    Tema("salud", "Salud y cuerpo", "🩺"),
    Tema("clima", "Clima y naturaleza", "🌦️"),
    Tema("estudio", "Estudio e idioma", "📚"),
    Tema("sentimientos", "Sentimientos y opiniones", "💬"),
    Tema("viaje", "Viajes", "✈️"),
    Tema("sociedad", "Sociedad y trámites", "🏛️"),
    Tema("gramatica", "Gramática", "🧩"),
)

TEMAS_POR_CLAVE: dict[str, Tema] = {t.clave: t for t in TEMAS}

#: Código de idioma para la voz del navegador. Si el celular no tiene voz
#: noruega instalada, la aplicación lo dice en vez de leer con acento español.
IDIOMA_VOZ: str = "nb-NO"

#: XP que da cada ejercicio acertado a la primera.
XP_ACIERTO: int = 10
#: XP extra por terminar una lección sin fallar ninguna.
XP_LECCION_PERFECTA: int = 25
#: XP por completar una lección.
XP_LECCION: int = 20
#: Vidas con las que empieza una lección. Al perderlas todas hay que repetirla.
VIDAS_POR_LECCION: int = 5


class Dificultad(int, Enum):
    """Qué tan difícil es un elemento, para escoger cuándo mostrarlo."""

    MUY_FACIL = 1
    FACIL = 2
    MEDIA = 3
    DIFICIL = 4
    MUY_DIFICIL = 5
