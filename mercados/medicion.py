"""Medir si los patrones cumplen lo que el libro promete.

El libro afirma que «la probabilidad de que el precio vaya en la dirección que
esperas es al menos por encima de un 50%», y le pone a cada patrón una
etiqueta —*fiabilidad muy alta*, *baja*— **sin publicar un solo número ni una
sola muestra que lo respalde**.

Este módulo no repite esa afirmación: la comprueba. Para cada aparición del
patrón en el histórico mira qué pasó de verdad en las sesiones siguientes y
entrega el porcentaje real con:

1. **el número de casos**, porque un 80 % sobre 5 apariciones no es nada;
2. **el intervalo de confianza**, que dice cuánto puede moverse ese número;
3. **la tasa base**, que es la comparación que de verdad importa: si el precio
   sube el 54 % de los días de todos modos, un patrón que acierta el 55 % no
   está diciendo absolutamente nada.

Sin el punto 3, cualquier patrón alcista parece funcionar en un mercado que
viene subiendo. Ese es el error clásico, y aquí no se comete.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from .dominio import Sentimiento, Vela
from .patrones import PATRONES, Aparicion, Patron, buscar

#: Horizontes que se miden, en sesiones. El libro habla de «la vela de
#: confirmación siguiente», de ahí que 1 sea el primero.
HORIZONTES: tuple[int, ...] = (1, 3, 5, 10)

#: Por debajo de esta cantidad de casos, no se concluye nada. No es un número
#: mágico: es el mínimo con el que un intervalo de confianza deja de ser tan
#: ancho que abarca cualquier respuesta.
CASOS_MINIMOS = 30

#: Confianza del 95 % para UNA sola pregunta.
ALFA = 0.05


def z_para(pruebas: int = 1) -> float:
    """El z del intervalo, corregido por cuántas preguntas se hacen a la vez.

    ESTO NO ES UN ADORNO ESTADÍSTICO. Aquí se miden 28 patrones contra 4
    horizontes: 112 preguntas de una sentada. Con el 95 % de siempre, una de
    cada veinte da «significativo» **por pura casualidad**, así que unas seis
    de esas 112 iban a parecer buenas aunque los patrones no sirvieran para
    nada. Se comprobó con datos completamente aleatorios: salían «hallazgos».

    La corrección de Bonferroni reparte el margen de error entre todas las
    preguntas (alfa / número de pruebas) y con eso los falsos hallazgos
    desaparecen. El precio es un intervalo más ancho, que es exactamente lo
    honesto: preguntar muchas cosas a la vez da menos derecho a creerse cada
    respuesta.
    """
    alfa = ALFA / max(1, pruebas)
    return statistics.NormalDist().inv_cdf(1 - alfa / 2)


#: El z de siempre, para una sola pregunta.
Z = z_para(1)


def wilson(aciertos: int, casos: int, pruebas: int = 1) -> tuple[float, float]:
    """Intervalo de confianza de una proporción (método de Wilson).

    Se usa Wilson y no la fórmula normal de siempre porque con pocos casos
    —que es justo lo que va a pasar con los patrones raros— la normal da
    intervalos que se salen de 0–1 y engañan.
    """
    if casos <= 0:
        return (0.0, 1.0)
    z = z_para(pruebas)
    p = aciertos / casos
    denominador = 1 + z * z / casos
    centro = (p + z * z / (2 * casos)) / denominador
    margen = (z / denominador) * math.sqrt(p * (1 - p) / casos + z * z / (4 * casos * casos))
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def _rendimiento(velas: Sequence[Vela], desde: int, sesiones: int) -> float | None:
    """Cuánto se movió el cierre `sesiones` después, en tanto por uno."""
    hasta = desde + sesiones
    if hasta >= len(velas):
        return None  # no se mira lo que todavía no pasó
    base = velas[desde].cierre
    if base == 0:
        return None
    return (velas[hasta].cierre - base) / base


def tasa_base(velas: Sequence[Vela], sesiones: int, signo: int) -> tuple[int, int]:
    """Cuántas veces, de TODAS las sesiones, el precio fue en esa dirección.

    Es el listón contra el que hay que comparar cualquier patrón.
    """
    if signo == 0:
        return (0, 0)
    aciertos = casos = 0
    for i in range(len(velas)):
        r = _rendimiento(velas, i, sesiones)
        if r is None:
            continue
        casos += 1
        if r * signo > 0:
            aciertos += 1
    return (aciertos, casos)


@dataclass(frozen=True)
class Resultado:
    """Lo que de verdad pasó tras un patrón, a un horizonte dado."""

    patron: Patron
    sesiones: int
    casos: int
    aciertos: int
    rendimiento_medio: float
    base_aciertos: int
    base_casos: int
    #: Cuántas preguntas se hicieron en la misma tanda. Ensancha el margen:
    #: ver `z_para`.
    pruebas: int = 1

    @property
    def tasa(self) -> float:
        return self.aciertos / self.casos if self.casos else 0.0

    @property
    def intervalo(self) -> tuple[float, float]:
        return wilson(self.aciertos, self.casos, self.pruebas)

    @property
    def tasa_base(self) -> float:
        return self.base_aciertos / self.base_casos if self.base_casos else 0.0

    @property
    def ventaja(self) -> float:
        """Cuánto mejor —o peor— que no mirar nada."""
        return self.tasa - self.tasa_base

    @property
    def medible(self) -> bool:
        """Los patrones neutros no prometen dirección: no hay qué comprobar."""
        return self.patron.sentimiento is not Sentimiento.NEUTRO

    @property
    def veredicto(self) -> str:
        """La conclusión honesta, en una línea."""
        if not self.medible:
            return "El libro no le atribuye dirección: no hay nada que medir."
        if self.casos == 0:
            return "No apareció ni una vez en este histórico."
        if self.casos < CASOS_MINIMOS:
            return (
                f"Solo {self.casos} apariciones: no alcanza para concluir nada "
                f"(harían falta al menos {CASOS_MINIMOS})."
            )
        bajo, alto = self.intervalo
        if bajo <= self.tasa_base <= alto:
            return (
                "No se distingue de no mirar nada: el margen de error abarca "
                f"la tasa base ({self.tasa_base:.0%})."
            )
        if self.tasa > self.tasa_base:
            return f"Acierta {self.ventaja:+.0%} por encima de la tasa base."
        return f"Acierta {self.ventaja:+.0%} por DEBAJO de la tasa base."

    @property
    def contradice_al_libro(self) -> bool:
        """¿El libro lo vende como fiable y la historia no lo respalda?"""
        if not self.medible or self.casos < CASOS_MINIMOS:
            return False
        promete_mucho = self.patron.fiabilidad_declarada.value in ("muy_alta", "alta")
        bajo, alto = self.intervalo
        no_supera = bajo <= self.tasa_base <= alto or self.tasa <= self.tasa_base
        return promete_mucho and no_supera


def medir(
    velas: Sequence[Vela],
    patron: Patron,
    sesiones: int,
    apariciones: Sequence[Aparicion] | None = None,
    pruebas: int = 1,
) -> Resultado:
    """Qué pasó después de cada aparición de un patrón."""
    if apariciones is None:
        apariciones = [a for a in buscar(velas, [patron.clave])]
    signo = patron.sentimiento.signo
    aciertos = casos = 0
    suma = 0.0
    for a in apariciones:
        r = _rendimiento(velas, a.indice, sesiones)
        if r is None:
            continue
        casos += 1
        suma += r
        if signo and r * signo > 0:
            aciertos += 1
    base_aciertos, base_casos = tasa_base(velas, sesiones, signo)
    return Resultado(
        patron=patron,
        sesiones=sesiones,
        casos=casos,
        aciertos=aciertos,
        rendimiento_medio=(suma / casos) if casos else 0.0,
        base_aciertos=base_aciertos,
        base_casos=base_casos,
        pruebas=pruebas,
    )


def medir_todo(velas: Sequence[Vela], horizontes: Sequence[int] = HORIZONTES) -> list[Resultado]:
    """Los 28 patrones contra todos los horizontes, de una sola pasada."""
    todas = buscar(velas)
    por_patron: dict[str, list[Aparicion]] = {p.clave: [] for p in PATRONES}
    for a in todas:
        por_patron[a.patron.clave].append(a)
    # Cuántas preguntas se hacen en total: cada patrón contra cada horizonte.
    # Ese número ensancha el margen de todos, y por eso se calcula antes.
    pruebas = len(PATRONES) * len(horizontes)
    return [
        medir(velas, patron, sesiones, por_patron[patron.clave], pruebas=pruebas)
        for patron in PATRONES
        for sesiones in horizontes
    ]
