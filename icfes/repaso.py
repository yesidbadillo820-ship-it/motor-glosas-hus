"""Repaso espaciado: qué repasar y cuándo, para no olvidar lo estudiado.

El problema real de una preparación de un año no es aprender: es **no olvidar**
lo que se aprendió en marzo cuando llega agosto. La curva del olvido dice que
lo estudiado una sola vez se pierde en días; lo repasado justo antes de
olvidarlo se queda por meses.

Este módulo implementa una versión del algoritmo SM-2 (el mismo de Anki),
adaptado en dos cosas para el ICFES:

1. **Nunca programa un repaso después del examen.** Un repaso el 3 de
   septiembre no le sirve a nadie que presenta el 8 de agosto.
2. **Traduce el desempeño real en una calificación.** El estudiante no tiene
   que decidir «esto fue un 4 o un 3»: el sistema lo deduce de si acertó, de
   cuánto se demoró y de por qué falló.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from .dominio import CausaError

#: Facilidad mínima. Por debajo de esto los repasos se vuelven tan seguidos
#: que el estudiante nunca avanza a temas nuevos.
FACILIDAD_MINIMA: float = 1.3

#: Facilidad de una tarjeta nueva, tal como la define SM-2.
FACILIDAD_INICIAL: float = 2.5

#: Intervalos fijos de los dos primeros repasos, en días.
PRIMER_INTERVALO: int = 1
SEGUNDO_INTERVALO: int = 6

#: A partir de este puntaje de calidad se considera que la respuesta fue buena.
CALIDAD_APROBATORIA: int = 3


@dataclass(frozen=True)
class Tarjeta:
    """Un tema o una pregunta que está en el ciclo de repaso.

    Atributos:
        clave: qué se repasa (el id de una pregunta o el nombre de un tema).
        repeticiones: cuántas veces seguidas se ha respondido bien.
        facilidad: qué tan fácil resulta; sube con los aciertos y baja con los
            fallos. Multiplica el intervalo entre repasos.
        intervalo_dias: cuántos días se dejó pasar hasta este repaso.
        proxima_fecha: cuándo toca volver a verla.
    """

    clave: str
    repeticiones: int = 0
    facilidad: float = FACILIDAD_INICIAL
    intervalo_dias: int = 0
    proxima_fecha: date | None = None

    @property
    def es_nueva(self) -> bool:
        """¿Nunca se ha repasado?"""
        return self.repeticiones == 0 and self.proxima_fecha is None

    def vence(self, hoy: date) -> bool:
        """¿Ya toca repasarla?"""
        return self.proxima_fecha is None or self.proxima_fecha <= hoy


def calidad_desde_respuesta(
    acerto: bool,
    segundos: float | None = None,
    causa: CausaError | None = None,
    segundos_de_referencia: float = 120.0,
) -> int:
    """Traduce lo que pasó al responder en una calificación de 0 a 5.

    La idea: acertar rápido no es lo mismo que acertar a las malas, y fallar
    por descuido no es lo mismo que fallar porque no se sabe el tema.

    - Falló por no saber el tema o adivinando → 0 (se reinicia el ciclo).
    - Falló por otra causa → 1 o 2 (se reinicia, pero con menos castigo).
    - Acertó lento → 3.
    - Acertó en un tiempo normal → 4.
    - Acertó rápido → 5.
    """
    if not acerto:
        if causa in (CausaError.CONCEPTO, CausaError.ADIVINE):
            return 0
        if causa in (CausaError.DESCUIDO, CausaError.TIEMPO):
            return 2
        return 1
    if segundos is None:
        return 4
    if segundos > segundos_de_referencia * 1.5:
        return 3
    if segundos > segundos_de_referencia * 0.6:
        return 4
    return 5


def calificar(
    tarjeta: Tarjeta,
    calidad: int,
    hoy: date,
    fecha_examen: date | None = None,
) -> Tarjeta:
    """Actualiza la tarjeta después de repasarla y calcula el próximo repaso.

    Args:
        tarjeta: cómo venía la tarjeta.
        calidad: de 0 a 5, normalmente de :func:`calidad_desde_respuesta`.
        hoy: la fecha del repaso.
        fecha_examen: si se pasa, ningún repaso queda programado después del
            examen: se adelanta al día anterior. Un repaso posterior al examen
            no sirve para nada.

    Returns:
        Una tarjeta nueva (las tarjetas no se modifican, se reemplazan).
    """
    if not 0 <= calidad <= 5:
        raise ValueError("La calidad de un repaso va de 0 a 5")

    if calidad < CALIDAD_APROBATORIA:
        # Se falló: el ciclo vuelve a empezar y mañana se repite.
        repeticiones = 0
        intervalo = PRIMER_INTERVALO
    else:
        repeticiones = tarjeta.repeticiones + 1
        if repeticiones == 1:
            intervalo = PRIMER_INTERVALO
        elif repeticiones == 2:
            intervalo = SEGUNDO_INTERVALO
        else:
            intervalo = max(1, round(tarjeta.intervalo_dias * tarjeta.facilidad))

    # La facilidad se ajusta según qué tan bien salió (fórmula de SM-2).
    ajuste = 0.1 - (5 - calidad) * (0.08 + (5 - calidad) * 0.02)
    facilidad = max(FACILIDAD_MINIMA, tarjeta.facilidad + ajuste)

    proxima = hoy + timedelta(days=intervalo)
    if fecha_examen is not None and proxima >= fecha_examen:
        # Se adelanta al día anterior al examen, nunca después.
        proxima = max(hoy + timedelta(days=1), fecha_examen - timedelta(days=1))

    return replace(
        tarjeta,
        repeticiones=repeticiones,
        facilidad=round(facilidad, 4),
        intervalo_dias=intervalo,
        proxima_fecha=proxima,
    )


def pendientes(tarjetas: list[Tarjeta], hoy: date, limite: int | None = None) -> list[Tarjeta]:
    """Las tarjetas que toca repasar hoy, de la más atrasada a la más reciente.

    Se ordenan por fecha de vencimiento: lo más atrasado primero, porque es lo
    que está más cerca de olvidarse. Si se pasa un ``limite``, se devuelven
    solo las primeras: más vale hacer 20 repasos bien que 90 de afán.
    """
    vencidas = [t for t in tarjetas if t.vence(hoy)]
    vencidas.sort(key=lambda t: (t.proxima_fecha or date.min, t.facilidad))
    return vencidas[:limite] if limite else vencidas


def carga_proxima(tarjetas: list[Tarjeta], hoy: date, dias: int = 7) -> dict[date, int]:
    """Cuántos repasos caen cada día de los próximos ``dias``.

    Sirve para avisar a tiempo: «el jueves te caen 60 repasos, adelanta algo
    hoy». Sin esto, el repaso espaciado se acumula y se abandona.
    """
    if dias <= 0:
        raise ValueError("Hay que mirar al menos un día")
    agenda = {hoy + timedelta(days=i): 0 for i in range(dias)}
    for t in tarjetas:
        fecha = t.proxima_fecha or hoy
        if fecha < hoy:
            fecha = hoy
        if fecha in agenda:
            agenda[fecha] += 1
    return agenda
