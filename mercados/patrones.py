"""Los 28 patrones del libro, cada uno como una regla comprobable.

Regla de la casa, la misma del motor de glosas: **no se inventa nada**. Cada
detector implementa la definición que el libro da, ni más ni menos. Cuando la
literatura clásica añade una condición que el libro no menciona, no se agrega
a escondidas: se anota en `catalogo/patrones.json` con `"revisar": true` para
que quede a la vista.

Fuente: Luis M. González, *Velas Japonesas: patrones simples y combinados*
(detrading.org). La página de cada patrón está en el catálogo.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .dominio import (
    UMBRAL_CUERPO_PEQUENO,
    UMBRAL_DOJI,
    UMBRAL_MECHA_CORTA,
    VECES_ELEFANTE,
    VECES_MECHA_LARGA,
    VENTANA_PROMEDIO,
    VENTANA_TENDENCIA,
    Familia,
    Fiabilidad,
    Sentimiento,
    Vela,
)


@dataclass(frozen=True)
class Contexto:
    """Una posición del histórico, con lo que hace falta para juzgarla.

    `fin` es el índice de la ÚLTIMA vela del patrón. Las anteriores se piden
    con `atras(1)`, `atras(2)`… porque así se leen los patrones: de la última
    hacia atrás.
    """

    velas: Sequence[Vela]
    fin: int
    largo: int = 1

    def atras(self, cuantas: int = 0) -> Vela:
        return self.velas[self.fin - cuantas]

    @property
    def inicio(self) -> int:
        """Índice de la primera vela del patrón."""
        return self.fin - self.largo + 1

    @property
    def cuerpo_promedio(self) -> float:
        """El cuerpo típico de las sesiones ANTERIORES al patrón.

        Sin esto, «vela grande» no significa nada: un cuerpo de 2 pesos es
        enorme en una acción de 20 y despreciable en una de 20.000.
        """
        desde = max(0, self.inicio - VENTANA_PROMEDIO)
        previas = self.velas[desde : self.inicio]
        if not previas:
            return 0.0
        return sum(v.cuerpo for v in previas) / len(previas)

    @property
    def tendencia_previa(self) -> str:
        """«alcista», «bajista» o «lateral» antes de que empiece el patrón.

        Casi todos los patrones del libro solo valen si vienen después de una
        tendencia («aparece después de una tendencia bajista»). Sin esta
        comprobación, un martillo en medio de un mercado plano contaría igual
        que uno al final de una caída, que es justo lo que el libro dice que NO.
        """
        desde = self.inicio - VENTANA_TENDENCIA
        if desde < 0:
            return "desconocida"
        arranque = self.velas[desde].cierre
        remate = self.velas[self.inicio - 1].cierre
        if arranque == 0:
            return "desconocida"
        cambio = (remate - arranque) / abs(arranque)
        if cambio <= -0.01:
            return "bajista"
        if cambio >= 0.01:
            return "alcista"
        return "lateral"

    # -------------------------------------------------------------- atajos --
    def venia_bajando(self) -> bool:
        return self.tendencia_previa == "bajista"

    def venia_subiendo(self) -> bool:
        return self.tendencia_previa == "alcista"


# ---------------------------------------------------------------- auxiliares
def sin_cuerpo(v: Vela) -> bool:
    """«Precio de cierre igual al precio de apertura» — con tolerancia real."""
    return v.rango > 0 and v.cuerpo <= UMBRAL_DOJI * v.rango


def cuerpo_pequeno(v: Vela) -> bool:
    return v.rango > 0 and v.cuerpo <= UMBRAL_CUERPO_PEQUENO * v.rango


def mecha_superior_corta(v: Vela) -> bool:
    return v.rango > 0 and v.mecha_superior <= UMBRAL_MECHA_CORTA * v.rango


def mecha_inferior_corta(v: Vela) -> bool:
    return v.rango > 0 and v.mecha_inferior <= UMBRAL_MECHA_CORTA * v.rango


def mecha_inferior_larga(v: Vela) -> bool:
    """«Al menos dos veces el tamaño del cuerpo», textual del libro."""
    return v.cuerpo > 0 and v.mecha_inferior >= VECES_MECHA_LARGA * v.cuerpo


def mecha_superior_larga(v: Vela) -> bool:
    return v.cuerpo > 0 and v.mecha_superior >= VECES_MECHA_LARGA * v.cuerpo


def es_elefante(v: Vela, promedio: float) -> bool:
    """«Cuerpo al menos 3 veces mayor que el de las velas promedio anteriores»."""
    return promedio > 0 and v.cuerpo >= VECES_ELEFANTE * promedio


def gap_bajista(actual: Vela, anterior: Vela) -> bool:
    """Abre por debajo de todo el cuerpo de la vela anterior."""
    return actual.cima_cuerpo < anterior.base_cuerpo


def gap_alcista(actual: Vela, anterior: Vela) -> bool:
    return actual.base_cuerpo > anterior.cima_cuerpo


# =========================================================================== #
#  PATRONES INDIVIDUALES — reversión o cambio                                 #
# =========================================================================== #
def doji_libelula(c: Contexto) -> bool:
    v = c.atras()
    # No se le pide la regla del «doble del cuerpo»: una libélula NO TIENE
    # cuerpo, así que esa comparación es imposible por definición. Lo que la
    # define es que la mecha inferior se coma la vela entera.
    return (
        sin_cuerpo(v)
        and v.mecha_inferior >= 0.6 * v.rango
        and mecha_superior_corta(v)
        and c.venia_bajando()
    )


def martillo(c: Contexto) -> bool:
    v = c.atras()
    return (
        cuerpo_pequeno(v)
        and mecha_inferior_larga(v)
        and mecha_superior_corta(v)
        and c.venia_bajando()
    )


def martillo_invertido(c: Contexto) -> bool:
    v = c.atras()
    return (
        cuerpo_pequeno(v)
        and mecha_superior_larga(v)
        and mecha_inferior_corta(v)
        and c.venia_bajando()
    )


def lapida_doji(c: Contexto) -> bool:
    v = c.atras()
    return (
        sin_cuerpo(v)
        and v.mecha_superior >= 0.6 * v.rango
        and mecha_inferior_corta(v)
        and c.venia_subiendo()
    )


def hombre_colgado(c: Contexto) -> bool:
    """El martillo, pero al final de una subida: ahí el libro lo lee al revés."""
    v = c.atras()
    return (
        cuerpo_pequeno(v)
        and mecha_inferior_larga(v)
        and mecha_superior_corta(v)
        and c.venia_subiendo()
    )


def estrella_fugaz(c: Contexto) -> bool:
    v = c.atras()
    return (
        cuerpo_pequeno(v)
        and mecha_superior_larga(v)
        and mecha_inferior_corta(v)
        and c.venia_subiendo()
    )


# =========================================================================== #
#  PATRONES INDIVIDUALES — confirmación o continuidad                         #
# =========================================================================== #
def marubozu_blanca(c: Contexto) -> bool:
    v = c.atras()
    return (
        v.alcista
        and mecha_superior_corta(v)
        and mecha_inferior_corta(v)
        and v.cuerpo >= 0.8 * v.rango
        and v.cuerpo >= c.cuerpo_promedio
    )


def marubozu_negra(c: Contexto) -> bool:
    v = c.atras()
    return (
        v.bajista
        and mecha_superior_corta(v)
        and mecha_inferior_corta(v)
        and v.cuerpo >= 0.8 * v.rango
        and v.cuerpo >= c.cuerpo_promedio
    )


def elefante_verde(c: Contexto) -> bool:
    v = c.atras()
    return (
        v.alcista
        and es_elefante(v, c.cuerpo_promedio)
        and mecha_superior_corta(v)
        and mecha_inferior_corta(v)
    )


def elefante_rojo(c: Contexto) -> bool:
    v = c.atras()
    return (
        v.bajista
        and es_elefante(v, c.cuerpo_promedio)
        and mecha_superior_corta(v)
        and mecha_inferior_corta(v)
    )


# =========================================================================== #
#  PATRONES INDIVIDUALES — indecisión                                         #
# =========================================================================== #
def doji(c: Contexto) -> bool:
    """Doji «a secas»: sin cuerpo y con las dos mechas cortas y parecidas.

    Se excluyen la libélula y la lápida a propósito: el libro las trata como
    patrones distintos, con dirección propia, y contarlas dos veces inflaría
    cualquier medición.
    """
    v = c.atras()
    if not sin_cuerpo(v) or v.rango <= 0:
        return False
    if v.mecha_superior >= 0.6 * v.rango or v.mecha_inferior >= 0.6 * v.rango:
        return False
    mayor = max(v.mecha_superior, v.mecha_inferior)
    menor = min(v.mecha_superior, v.mecha_inferior)
    return mayor > 0 and menor >= 0.5 * mayor


def peonza(c: Contexto) -> bool:
    v = c.atras()
    return (
        not sin_cuerpo(v)
        and cuerpo_pequeno(v)
        and v.mecha_superior >= 0.2 * v.rango
        and v.mecha_inferior >= 0.2 * v.rango
    )


# =========================================================================== #
#  PATRONES COMBINADOS — reversión alcista                                    #
# =========================================================================== #
def pauta_penetrante(c: Contexto) -> bool:
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.bajista
        and primera.cuerpo >= c.cuerpo_promedio
        and segunda.alcista
        and segunda.apertura < primera.minimo
        and segunda.cierre > (primera.apertura + primera.cierre) / 2
        and segunda.cierre < primera.apertura
        and c.venia_bajando()
    )


def pauta_envolvente_alcista(c: Contexto) -> bool:
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.bajista
        and segunda.alcista
        and segunda.base_cuerpo < primera.base_cuerpo
        and segunda.cima_cuerpo > primera.cima_cuerpo
        and c.venia_bajando()
    )


def harami_alcista(c: Contexto) -> bool:
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.cuerpo >= c.cuerpo_promedio
        and not es_elefante(primera, c.cuerpo_promedio)
        and segunda.cuerpo < primera.cuerpo
        and segunda.maximo <= primera.cima_cuerpo
        and segunda.minimo >= primera.base_cuerpo
        and c.venia_bajando()
    )


def tres_soldados_blancos(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    if not (primera.alcista and segunda.alcista and tercera.alcista):
        return False
    if not all(v.cuerpo >= c.cuerpo_promedio for v in (primera, segunda, tercera)):
        return False
    if not (segunda.cierre > primera.cierre and tercera.cierre > segunda.cierre):
        return False
    # «La apertura de cada vela está dentro del cuerpo de la anterior,
    #  comenzando por la segunda» — la primera no cuenta.
    dentro = (
        primera.base_cuerpo <= segunda.apertura <= primera.cima_cuerpo
        and segunda.base_cuerpo <= tercera.apertura <= segunda.cima_cuerpo
    )
    return dentro and c.venia_bajando()


def tres_estrellas_del_sur(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    if not (primera.bajista and segunda.bajista and tercera.bajista):
        return False
    # «Marubozu abierto»: abre en el máximo, cierra por encima del mínimo,
    # con mecha inferior larga.
    primera_ok = (
        abs(primera.apertura - primera.maximo) <= UMBRAL_MECHA_CORTA * primera.rango
        and primera.mecha_inferior >= primera.cuerpo
    )
    segunda_ok = segunda.cuerpo < primera.cuerpo and segunda.minimo > primera.minimo
    tercera_ok = tercera.cuerpo < segunda.cuerpo and tercera.rango <= segunda.rango
    return primera_ok and segunda_ok and tercera_ok and c.venia_bajando()


def estrella_de_la_manana(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    return (
        primera.bajista
        and es_elefante(primera, c.cuerpo_promedio)
        and cuerpo_pequeno(segunda)
        and gap_bajista(segunda, primera)
        and tercera.alcista
        and gap_alcista(tercera, segunda)
        and c.venia_bajando()
    )


def bebe_abandonado_alcista(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    return (
        primera.bajista
        and primera.cuerpo >= c.cuerpo_promedio
        and sin_cuerpo(segunda)
        and segunda.maximo < primera.minimo
        and tercera.alcista
        and tercera.minimo > segunda.maximo
        and c.venia_bajando()
    )


def toro_180(c: Contexto) -> bool:
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.bajista
        and es_elefante(primera, c.cuerpo_promedio)
        and segunda.alcista
        and es_elefante(segunda, c.cuerpo_promedio)
        and c.venia_bajando()
    )


# =========================================================================== #
#  PATRONES COMBINADOS — reversión bajista                                    #
# =========================================================================== #
def tres_cuervos_negros(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    if not (primera.bajista and segunda.bajista and tercera.bajista):
        return False
    if not all(v.cuerpo >= c.cuerpo_promedio for v in (primera, segunda, tercera)):
        return False
    if not (segunda.cierre < primera.cierre and tercera.cierre < segunda.cierre):
        return False
    dentro = (
        primera.base_cuerpo <= segunda.apertura <= primera.cima_cuerpo
        and segunda.base_cuerpo <= tercera.apertura <= segunda.cima_cuerpo
    )
    return dentro and c.venia_subiendo()


def estrella_vespertina(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    return (
        primera.alcista
        and primera.cuerpo >= c.cuerpo_promedio
        and cuerpo_pequeno(segunda)
        and gap_alcista(segunda, primera)
        and tercera.bajista
        and tercera.apertura < segunda.base_cuerpo
        and primera.base_cuerpo < tercera.cierre < primera.cima_cuerpo
        and c.venia_subiendo()
    )


def bebe_abandonado_bajista(c: Contexto) -> bool:
    tercera, segunda, primera = c.atras(0), c.atras(1), c.atras(2)
    return (
        primera.alcista
        and primera.cuerpo >= c.cuerpo_promedio
        and sin_cuerpo(segunda)
        and segunda.minimo > primera.maximo
        and tercera.bajista
        and tercera.maximo < segunda.minimo
        and c.venia_subiendo()
    )


def cubierta_de_la_nube_oscura(c: Contexto) -> bool:
    """Tal como lo define ESTE libro.

    OJO: la literatura clásica exige además que la segunda vela cierre por
    debajo de la mitad del cuerpo verde. El libro no lo menciona, así que no
    se añade — queda anotado en el catálogo con `"revisar": true`.
    """
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.alcista
        and es_elefante(primera, c.cuerpo_promedio)
        and segunda.bajista
        and es_elefante(segunda, c.cuerpo_promedio)
        and segunda.apertura > primera.maximo
        and c.venia_subiendo()
    )


def harami_bajista(c: Contexto) -> bool:
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.cuerpo >= c.cuerpo_promedio
        and not es_elefante(primera, c.cuerpo_promedio)
        and segunda.cuerpo < primera.cuerpo
        and segunda.maximo <= primera.cima_cuerpo
        and segunda.minimo >= primera.base_cuerpo
        and c.venia_subiendo()
    )


def oso_180(c: Contexto) -> bool:
    segunda, primera = c.atras(0), c.atras(1)
    return (
        primera.alcista
        and es_elefante(primera, c.cuerpo_promedio)
        and segunda.bajista
        and es_elefante(segunda, c.cuerpo_promedio)
        and c.venia_subiendo()
    )


# =========================================================================== #
#  PATRONES COMBINADOS — confirmación o continuidad                           #
# =========================================================================== #
def triple_formacion_alcista(c: Contexto) -> bool:
    quinta = c.atras(0)
    medias = [c.atras(1), c.atras(2), c.atras(3)]
    primera = c.atras(4)
    return (
        primera.alcista
        and es_elefante(primera, c.cuerpo_promedio)
        and all(v.bajista and v.cuerpo < primera.cuerpo / 2 for v in medias)
        and quinta.alcista
        and quinta.cuerpo >= 0.7 * primera.cuerpo
        and c.venia_subiendo()
    )


def triple_formacion_bajista(c: Contexto) -> bool:
    quinta = c.atras(0)
    medias = [c.atras(1), c.atras(2), c.atras(3)]
    primera = c.atras(4)
    return (
        primera.bajista
        and es_elefante(primera, c.cuerpo_promedio)
        and all(v.alcista and v.cuerpo < primera.cuerpo / 2 for v in medias)
        and quinta.bajista
        and quinta.cuerpo >= 0.7 * primera.cuerpo
        and c.venia_bajando()
    )


# =========================================================================== #
#  El registro                                                                #
# =========================================================================== #
@dataclass(frozen=True)
class Patron:
    """Un patrón: cómo se llama, qué promete el libro y cómo se reconoce."""

    clave: str
    nombre: str
    velas: int
    familia: Familia
    sentimiento: Sentimiento
    fiabilidad_declarada: Fiabilidad
    pagina: int
    detectar: Callable[[Contexto], bool]


PATRONES: tuple[Patron, ...] = (
    # --- individuales · reversión -----------------------------------------
    Patron(
        "doji_libelula",
        "Doji Libélula",
        1,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.ALTA,
        12,
        doji_libelula,
    ),
    Patron(
        "martillo",
        "Vela Martillo",
        1,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.BAJA,
        14,
        martillo,
    ),
    Patron(
        "martillo_invertido",
        "Martillo Invertido",
        1,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.MODERADA,
        16,
        martillo_invertido,
    ),
    Patron(
        "lapida_doji",
        "Lápida Doji",
        1,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.MODERADA,
        18,
        lapida_doji,
    ),
    Patron(
        "hombre_colgado",
        "Hombre Colgado",
        1,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.BAJA,
        20,
        hombre_colgado,
    ),
    Patron(
        "estrella_fugaz",
        "Estrella Fugaz",
        1,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.BAJA,
        22,
        estrella_fugaz,
    ),
    # --- individuales · continuidad ---------------------------------------
    Patron(
        "marubozu_blanca",
        "Marubozu Blanca",
        1,
        Familia.CONTINUIDAD,
        Sentimiento.ALCISTA,
        Fiabilidad.BAJA,
        25,
        marubozu_blanca,
    ),
    Patron(
        "elefante_verde",
        "Elefante Verde",
        1,
        Familia.CONTINUIDAD,
        Sentimiento.ALCISTA,
        Fiabilidad.MUY_ALTA,
        27,
        elefante_verde,
    ),
    Patron(
        "marubozu_negra",
        "Marubozu Negra",
        1,
        Familia.CONTINUIDAD,
        Sentimiento.BAJISTA,
        Fiabilidad.BAJA,
        29,
        marubozu_negra,
    ),
    Patron(
        "elefante_rojo",
        "Elefante Rojo",
        1,
        Familia.CONTINUIDAD,
        Sentimiento.BAJISTA,
        Fiabilidad.ALTA,
        31,
        elefante_rojo,
    ),
    # --- individuales · indecisión ----------------------------------------
    Patron(
        "doji", "Doji", 1, Familia.INDECISION, Sentimiento.NEUTRO, Fiabilidad.MODERADA, 34, doji
    ),
    Patron(
        "peonza", "Peonza", 1, Familia.INDECISION, Sentimiento.NEUTRO, Fiabilidad.BAJA, 36, peonza
    ),
    # --- combinados · reversión alcista -----------------------------------
    Patron(
        "pauta_penetrante",
        "Pauta Penetrante",
        2,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.MODERADA,
        40,
        pauta_penetrante,
    ),
    Patron(
        "pauta_envolvente_alcista",
        "Pauta Envolvente Alcista",
        2,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.ALTA,
        42,
        pauta_envolvente_alcista,
    ),
    Patron(
        "tres_soldados_blancos",
        "Tres Soldados Blancos",
        3,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.ALTA,
        44,
        tres_soldados_blancos,
    ),
    Patron(
        "harami_alcista",
        "Harami Alcista",
        2,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.BAJA,
        46,
        harami_alcista,
    ),
    Patron(
        "tres_estrellas_del_sur",
        "Tres Estrellas en el Sur",
        3,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.MODERADA,
        48,
        tres_estrellas_del_sur,
    ),
    Patron(
        "estrella_de_la_manana",
        "Estrella de la Mañana",
        3,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.MUY_ALTA,
        50,
        estrella_de_la_manana,
    ),
    Patron(
        "bebe_abandonado_alcista",
        "Bebé Abandonado Alcista",
        3,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.MUY_ALTA,
        52,
        bebe_abandonado_alcista,
    ),
    Patron(
        "toro_180",
        "Toro 180",
        2,
        Familia.REVERSION,
        Sentimiento.ALCISTA,
        Fiabilidad.ALTA,
        54,
        toro_180,
    ),
    # --- combinados · reversión bajista -----------------------------------
    Patron(
        "tres_cuervos_negros",
        "Tres Cuervos Negros",
        3,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.ALTA,
        56,
        tres_cuervos_negros,
    ),
    Patron(
        "estrella_vespertina",
        "Estrella Vespertina",
        3,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.ALTA,
        58,
        estrella_vespertina,
    ),
    Patron(
        "bebe_abandonado_bajista",
        "Bebé Abandonado Bajista",
        3,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.MUY_ALTA,
        60,
        bebe_abandonado_bajista,
    ),
    Patron(
        "cubierta_de_la_nube_oscura",
        "Cubierta de la Nube Oscura",
        2,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.ALTA,
        62,
        cubierta_de_la_nube_oscura,
    ),
    Patron(
        "harami_bajista",
        "Harami Bajista",
        2,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.BAJA,
        64,
        harami_bajista,
    ),
    Patron(
        "oso_180",
        "Oso 180",
        2,
        Familia.REVERSION,
        Sentimiento.BAJISTA,
        Fiabilidad.ALTA,
        66,
        oso_180,
    ),
    # --- combinados · continuidad -----------------------------------------
    Patron(
        "triple_formacion_alcista",
        "Triple Formación Alcista",
        5,
        Familia.CONTINUIDAD,
        Sentimiento.ALCISTA,
        Fiabilidad.ALTA,
        69,
        triple_formacion_alcista,
    ),
    Patron(
        "triple_formacion_bajista",
        "Triple Formación Bajista",
        5,
        Familia.CONTINUIDAD,
        Sentimiento.BAJISTA,
        Fiabilidad.ALTA,
        71,
        triple_formacion_bajista,
    ),
)

POR_CLAVE: dict[str, Patron] = {p.clave: p for p in PATRONES}


@dataclass(frozen=True)
class Aparicion:
    """Un patrón encontrado en una posición concreta del histórico."""

    patron: Patron
    indice: int  # índice de la ÚLTIMA vela del patrón
    velas: tuple[Vela, ...]

    @property
    def fecha(self):
        return self.velas[-1].fecha


def buscar(velas: Sequence[Vela], claves: Sequence[str] | None = None) -> list[Aparicion]:
    """Todas las apariciones de todos los patrones, en orden de fecha."""
    elegidos = [POR_CLAVE[c] for c in claves] if claves else list(PATRONES)
    salida: list[Aparicion] = []
    for i in range(len(velas)):
        for patron in elegidos:
            if i - patron.velas + 1 < 0:
                continue
            contexto = Contexto(velas, fin=i, largo=patron.velas)
            if patron.detectar(contexto):
                trozo = tuple(velas[contexto.inicio : i + 1])
                salida.append(Aparicion(patron, i, trozo))
    salida.sort(key=lambda a: (a.indice, a.patron.clave))
    return salida
