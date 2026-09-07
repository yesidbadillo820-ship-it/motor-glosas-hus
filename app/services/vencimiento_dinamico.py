"""Días restantes del plazo legal, calculados EN CALIENTE (V2, Pilar 4).

03-09-2026. La columna `dias_restantes` se escribe una vez, al analizar la
glosa, y queda congelada. La primera corrección intentó refrescarla con un
barrido periódico que la reescribía en la base; se descartó por decisión del
auditor: el tiempo es continuo y no se persiste — se calcula al leer.

Este módulo es ese cálculo: días hábiles que quedan del plazo de 20 días
(Art. 57 Ley 1438/2011), cruzando la fecha de radicación contra la fecha de
HOY, descontando fines de semana y festivos colombianos (`FERIADOS_CO`, el
mismo calendario que usa el motor para la extemporaneidad — una sola verdad).

Quién lo usa: `motor_vencimientos.evaluar()` lo aplica a cada glosa en juego
al momento de responder la consulta, así que el tablero, los correos y la
pantalla ven siempre el valor de hoy sin que nadie escriba nada en la base.
La columna guardada queda solo como respaldo para glosas sin fechas.

Reglas duras:
  - Sin fecha base no se inventa plazo: devuelve None y manda el respaldo.
  - El conteo se topa en 0 (0 = vencida, como ya lo leen tablero y pantalla).
  - A 3 días hábiles o menos (configurable), la glosa es CRÍTICA: rojo.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

# A cuántos días hábiles del vencimiento se pinta el rojo en pantalla.
UMBRAL_CRITICO_DIAS = 3


def umbral_critico() -> int:
    try:
        return max(0, int(os.getenv("VENCIMIENTOS_UMBRAL_CRITICO", UMBRAL_CRITICO_DIAS)))
    except (TypeError, ValueError):
        return UMBRAL_CRITICO_DIAS


def _a_fecha(v: Any) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def dias_restantes_hoy(fecha_base: Any, hoy: Optional[date] = None) -> Optional[int]:
    """Días hábiles que quedan del plazo legal, contados contra HOY.

    Consume un día por cada día hábil transcurrido DESPUÉS de la fecha base
    (el propio día de radicación no consume), saltando sábados, domingos y
    festivos colombianos. None si no hay fecha: sin fecha no hay plazo.
    """
    base = _a_fecha(fecha_base)
    if base is None:
        return None
    from app.services.extemporaneidad_texto import _cargar_feriados, _dias_habiles
    from app.services.glosa_service import DIAS_HABILES_LIMITE_EXTEMPORANEA

    hoy = hoy or date.today()
    if hoy <= base:
        return DIAS_HABILES_LIMITE_EXTEMPORANEA
    consumidos = _dias_habiles(base, hoy, _cargar_feriados())
    return max(0, DIAS_HABILES_LIMITE_EXTEMPORANEA - consumidos)


def dias_restantes_de(glosa: Any, hoy: Optional[date] = None) -> Optional[int]:
    """El plazo vivo de una glosa: radicación de la factura contra hoy.

    Sin fecha de radicación se usa la de recepción de la glosa; sin ninguna,
    None (y el que llama decide si usa el valor guardado como respaldo).
    """
    base = getattr(glosa, "fecha_radicacion_factura", None) or getattr(
        glosa, "fecha_recepcion", None
    )
    return dias_restantes_hoy(base, hoy)


def es_critica(dias: Optional[int], umbral: Optional[int] = None) -> bool:
    """¿Va en rojo? A `umbral` días hábiles o menos del vencimiento."""
    if dias is None:
        return False
    return dias <= (umbral if umbral is not None else umbral_critico())
