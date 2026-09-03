"""Demonio de vencimientos: el reloj del plazo legal vuelve a correr (V2, Pilar 4).

03-09-2026. El problema no era que faltara la alerta —`motor_vencimientos` ya
clasifica la urgencia y `alerta_service` ya arma el correo—: era que el número
que leen **estaba congelado**. `dias_restantes` se calcula UNA vez, cuando se
analiza la glosa, y se guarda en la tabla. Al día siguiente sigue diciendo lo
mismo. Una glosa que entró con 18 días de margen aparece con 18 días para
siempre, y el semáforo nunca se pone en rojo solo.

Eso fue exactamente lo que costó las tres facturas de junio descubiertas 45
días tarde: nadie mintió, el reloj simplemente no avanzaba.

Este módulo es el reloj. Barre en el fondo las glosas que siguen en juego,
recalcula los días hábiles que quedan del plazo legal de 20 días (Art. 57 de la
Ley 1438 de 2011) contra la fecha de HOY, y deja el número fresco en la base
para que el tablero, el correo y la pantalla vean la verdad.

A 3 días hábiles o menos, la glosa queda marcada como CRÍTICA para que la
pantalla la muestre en rojo.

Falla cerrado y en silencio: si una glosa no tiene fecha de recepción, no se
inventa un plazo — se deja como está. Y si el barrido cae, se registra y se
reintenta en la siguiente vuelta; nunca tumba el servidor.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from typing import Any, Optional

from app.core.logging_utils import logger

# Plazo legal para responder la glosa: 20 días hábiles (Art. 57 Ley 1438/2011).
# Es el mismo número que usa el motor al analizar; se importa de allá para que
# no existan dos verdades.
from app.services.glosa_service import DIAS_HABILES_LIMITE_EXTEMPORANEA

# A cuántos días hábiles del vencimiento se considera CRÍTICA (rojo en pantalla).
UMBRAL_CRITICO_DIAS = 3
# Cada cuánto barre el demonio. Media hora alcanza: el plazo se mide en días.
INTERVALO_MINUTOS = 30


def umbral_critico() -> int:
    try:
        return max(0, int(os.getenv("VENCIMIENTOS_UMBRAL_CRITICO", UMBRAL_CRITICO_DIAS)))
    except (TypeError, ValueError):
        return UMBRAL_CRITICO_DIAS


def intervalo_minutos() -> int:
    try:
        return max(1, int(os.getenv("VENCIMIENTOS_INTERVALO_MIN", INTERVALO_MINUTOS)))
    except (TypeError, ValueError):
        return INTERVALO_MINUTOS


def _a_fecha(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def dias_restantes_hoy(fecha_recepcion: Any, hoy: Optional[date] = None) -> Optional[int]:
    """Días hábiles que quedan del plazo legal, contados hasta HOY.

    Cuenta desde que la glosa llegó (fecha de recepción) hasta hoy y resta ese
    consumo de los 20 días hábiles de ley. Devuelve None si no hay fecha: sin
    fecha no hay plazo que calcular, y no se inventa.

    Se topa en 0 —igual que el motor al analizar—, así que 0 significa
    «vencida», que es como ya lo leen el tablero y la pantalla.
    """
    base = _a_fecha(fecha_recepcion)
    if base is None:
        return None
    hoy = hoy or date.today()
    if hoy < base:
        return DIAS_HABILES_LIMITE_EXTEMPORANEA
    # Reutiliza el contador de días hábiles del semáforo de preauditoría: una
    # sola implementación del calendario para todo el sistema.
    from app.services.preauditoria_service import _dias_habiles_entre

    consumidos = _dias_habiles_entre(base, hoy)
    return max(0, DIAS_HABILES_LIMITE_EXTEMPORANEA - consumidos)


def es_critica(dias: Optional[int], umbral: Optional[int] = None) -> bool:
    """¿Va en rojo? A `umbral` días hábiles o menos del vencimiento."""
    if dias is None:
        return False
    return dias <= (umbral if umbral is not None else umbral_critico())


def barrer(db: Any, hoy: Optional[date] = None, umbral: Optional[int] = None) -> dict:
    """Recalcula `dias_restantes` de las glosas que siguen en juego.

    Devuelve el parte del barrido: cuántas miró, cuántas cambiaron, cuántas
    quedaron críticas y cuántas ya vencidas. No toca las cerradas ni las que
    no tienen fecha de recepción.
    """
    from app.models.db import GlosaRecord
    from app.services.motor_vencimientos import esta_en_juego

    hoy = hoy or date.today()
    umb = umbral if umbral is not None else umbral_critico()
    revisadas = actualizadas = criticas = vencidas = 0

    for g in db.query(GlosaRecord).all():
        if not esta_en_juego(g):
            continue
        revisadas += 1
        nuevo = dias_restantes_hoy(getattr(g, "fecha_recepcion", None), hoy)
        if nuevo is None:
            continue
        if getattr(g, "dias_restantes", None) != nuevo:
            g.dias_restantes = nuevo
            actualizadas += 1
        if nuevo <= 0:
            vencidas += 1
        elif es_critica(nuevo, umb):
            criticas += 1

    if actualizadas:
        try:
            db.commit()
        except Exception as e:  # noqa: BLE001 — el barrido no puede tumbar nada
            logger.error(f"[VENCIMIENTOS] no se pudo guardar el barrido: {e}")
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return {
        "revisadas": revisadas,
        "actualizadas": actualizadas,
        "criticas": criticas,
        "vencidas": vencidas,
        "umbral_critico": umb,
    }


def barrer_con_sesion_propia() -> dict:
    """Un barrido con su propia sesión (para el bucle de fondo)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return barrer(db)
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass


async def bucle() -> None:
    """Barre cada cierto rato, para siempre. Nunca deja escapar una excepción:
    un barrido caído se registra y se reintenta en la vuelta siguiente."""
    espera = intervalo_minutos() * 60
    logger.info(f"[VENCIMIENTOS] demonio activo: barrido cada {intervalo_minutos()} min")
    while True:
        try:
            await asyncio.sleep(espera)
            parte = await asyncio.to_thread(barrer_con_sesion_propia)
            if parte["actualizadas"] or parte["criticas"] or parte["vencidas"]:
                logger.info(
                    f"[VENCIMIENTOS] {parte['revisadas']} en juego · "
                    f"{parte['actualizadas']} actualizadas · "
                    f"{parte['criticas']} críticas · {parte['vencidas']} vencidas"
                )
        except asyncio.CancelledError:
            logger.info("[VENCIMIENTOS] demonio detenido")
            raise
        except Exception as e:  # noqa: BLE001
            logger.error(f"[VENCIMIENTOS] barrido falló, se reintenta: {e}")


def debe_arrancar() -> bool:
    """En pruebas NO arranca: el lifespan se levanta cientos de veces y no
    tiene sentido dejar cientos de bucles dormidos. Se puede apagar en
    producción con VENCIMIENTOS_DEMONIO=0."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return (os.getenv("VENCIMIENTOS_DEMONIO", "1") or "1").strip() not in ("0", "false", "no")


def iniciar(app: Any) -> None:
    """Engancha el demonio al arranque de Uvicorn. Guarda la tarea en el app
    para poder cancelarla al apagar."""
    if not debe_arrancar():
        return
    try:
        app.state.tarea_vencimientos = asyncio.create_task(bucle())
    except Exception as e:  # noqa: BLE001 — jamás bloquea el arranque
        logger.error(f"[VENCIMIENTOS] no se pudo arrancar el demonio: {e}")


def detener(app: Any) -> None:
    tarea = getattr(getattr(app, "state", None), "tarea_vencimientos", None)
    if tarea is not None:
        tarea.cancel()
