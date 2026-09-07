"""Las piezas del análisis de velas japonesas.

Una vela resume una sesión con cuatro precios: apertura, máximo, mínimo y
cierre. Todo lo que este módulo hace sale de esos cuatro números —nada más—,
y por eso cada patrón se puede comprobar con una prueba en vez de discutirse.

Vocabulario del libro (Luis M. González, *Velas Japonesas: patrones simples y
combinados*, detrading.org) traducido a nombres de programa:

- **cuerpo**: distancia entre apertura y cierre.
- **mecha** o **sombra**: lo que sobresale del cuerpo, arriba o abajo.
- **alcista / verde**: cerró por encima de donde abrió.
- **bajista / roja**: cerró por debajo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Sentimiento(StrEnum):
    """Hacia dónde apunta el patrón, según el libro."""

    ALCISTA = "alcista"
    BAJISTA = "bajista"
    NEUTRO = "neutro"

    @property
    def etiqueta(self) -> str:
        return {"alcista": "Alcista", "bajista": "Bajista", "neutro": "Neutro"}[self.value]

    @property
    def signo(self) -> int:
        """+1 si el patrón espera subida, -1 bajada, 0 si no espera nada.

        Es lo que permite medirlo: sin una dirección esperada no hay nada
        que comprobar contra la historia.
        """
        return {"alcista": 1, "bajista": -1, "neutro": 0}[self.value]


class Familia(StrEnum):
    """Los tres «sentimientos de mercado» con que el libro agrupa los patrones."""

    REVERSION = "reversion"
    CONTINUIDAD = "continuidad"
    INDECISION = "indecision"

    @property
    def etiqueta(self) -> str:
        return {
            "reversion": "Reversión o cambio",
            "continuidad": "Confirmación o continuidad",
            "indecision": "Indecisión",
        }[self.value]


class Fiabilidad(StrEnum):
    """La etiqueta que el libro le pone a cada patrón.

    OJO: es la afirmación del autor, **no** una medición. El libro no publica
    ni un número ni una muestra que la respalde. Se guarda para poder
    contrastarla contra lo que de verdad pasó (ver `mercados/medicion.py`).
    """

    MUY_ALTA = "muy_alta"
    ALTA = "alta"
    MODERADA = "moderada"
    BAJA = "baja"

    @property
    def etiqueta(self) -> str:
        return {
            "muy_alta": "muy alta",
            "alta": "bastante alta",
            "moderada": "moderada",
            "baja": "baja",
        }[self.value]


@dataclass(frozen=True)
class Vela:
    """Una sesión: los cuatro precios y, si viene, el volumen."""

    fecha: date
    apertura: float
    maximo: float
    minimo: float
    cierre: float
    volumen: float | None = None

    def __post_init__(self) -> None:
        # Una vela con el máximo por debajo del mínimo no existe: es un archivo
        # mal armado, y callarlo haría que todos los patrones salieran mal sin
        # que nadie supiera por qué.
        if self.maximo < self.minimo:
            raise ValueError(f"{self.fecha}: el máximo ({self.maximo}) es menor que el mínimo")
        for nombre, precio in (("apertura", self.apertura), ("cierre", self.cierre)):
            if not (self.minimo - 1e-9 <= precio <= self.maximo + 1e-9):
                raise ValueError(
                    f"{self.fecha}: la {nombre} ({precio}) se sale del rango "
                    f"{self.minimo}–{self.maximo}"
                )

    # ---------------------------------------------------------------- medidas
    @property
    def cuerpo(self) -> float:
        """Tamaño del cuerpo, siempre positivo."""
        return abs(self.cierre - self.apertura)

    @property
    def rango(self) -> float:
        """De mínimo a máximo: todo lo que se movió el precio en la sesión."""
        return self.maximo - self.minimo

    @property
    def mecha_superior(self) -> float:
        return self.maximo - max(self.apertura, self.cierre)

    @property
    def mecha_inferior(self) -> float:
        return min(self.apertura, self.cierre) - self.minimo

    @property
    def cima_cuerpo(self) -> float:
        return max(self.apertura, self.cierre)

    @property
    def base_cuerpo(self) -> float:
        return min(self.apertura, self.cierre)

    # ---------------------------------------------------------------- colores
    @property
    def alcista(self) -> bool:
        """Verde: cerró por encima de donde abrió."""
        return self.cierre > self.apertura

    @property
    def bajista(self) -> bool:
        """Roja: cerró por debajo de donde abrió."""
        return self.cierre < self.apertura

    @property
    def color(self) -> str:
        return "verde" if self.alcista else "roja" if self.bajista else "plana"


#: Un cuerpo por debajo de esta fracción del rango cuenta como «sin cuerpo».
#: El libro dice «precio de cierre igual al precio de apertura», pero en datos
#: reales la igualdad exacta casi nunca ocurre: hay que dar una tolerancia o
#: no se detectaría ni un solo Doji en años de historia.
UMBRAL_DOJI = 0.05

#: Un cuerpo por debajo de esta fracción del rango es «cuerpo pequeño»
#: (martillo, peonza, harami).
UMBRAL_CUERPO_PEQUENO = 0.35

#: «Mecha al menos DOS veces el tamaño del cuerpo», textual del libro.
VECES_MECHA_LARGA = 2.0

#: Una mecha por debajo de esta fracción del rango es «ninguna o muy poca».
UMBRAL_MECHA_CORTA = 0.15

#: «Al menos 3 veces mayor al tamaño de las velas promedio anteriores»
#: (definición del Elefante en el libro).
VECES_ELEFANTE = 3.0

#: Cuántas sesiones anteriores se promedian para saber qué es «grande» aquí.
#: El tamaño de una vela solo significa algo comparado con las de al lado.
VENTANA_PROMEDIO = 10

#: Cuántas sesiones se miran hacia atrás para decidir la tendencia previa.
VENTANA_TENDENCIA = 5
