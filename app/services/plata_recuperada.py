"""Cuánta plata se glosó y en qué terminó — mes a mes y EPS por EPS.

Idea del 26-08-2026. El motor sabe cuánto se glosó, cuánto se respondió y
cuánto se levantó, pero eso no se veía junto en ninguna pantalla: hay 32
pantallas y una sola gráfica. Este es el número que pide la gerencia y el
que dice si el motor está sirviendo.

REGLA DE LA CASA — aquí no se estima nada
-----------------------------------------
Cada peso de este tablero sale de una columna de la base de datos. Cuando
una glosa no tiene el dato —una LEVANTADA a la que nadie le anotó el valor
recuperado, o una glosa sin fecha de vencimiento— **no se rellena con un
supuesto**: se cuenta aparte, en `sin_dato`, para que quien lea el tablero
sepa qué parte del total no está soportada. Un tablero que se inventa el
relleno miente con más autoridad que uno que se queda corto.

De dónde sale cada cifra
------------------------
  glosado                  suma de `valor_objetado` de todas las glosas del mes
  levantado                suma de `valor_recuperado` de las que la EPS marcó LEVANTADA
  ratificado               suma de `valor_objetado` de las marcadas RATIFICADA
  aceptado                 suma de `valor_objetado` de las marcadas ACEPTADA (el HUS pagó)
  sin_decision             suma de `valor_objetado` de las que la EPS aún no ha decidido
  respondido_a_tiempo      radicadas con fecha de radicación anterior o igual al vencimiento
  respondido_tarde         radicadas después del vencimiento
  perdido_por_vencimiento  sin radicar, sin decisión, y con el vencimiento ya pasado

El mes al que pertenece una glosa es el de `creado_en` — el día que entró
al motor. No se usa la fecha de la factura porque muchas no la traen.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.core.tz import a_utc, ahora_utc
from app.models.db import GlosaRecord

# Lo que la EPS puede responder. PENDIENTE cuenta como "aún no decidió".
_DECIDIDAS = ("LEVANTADA", "RATIFICADA", "ACEPTADA")

MESES_POR_DEFECTO = 6
MESES_MAXIMO = 24

_NOMBRE_MES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _casilla() -> dict:
    """Una casilla vacía del tablero — la misma para el mes y para la EPS."""
    return {
        "glosas": 0,
        "glosado": 0.0,
        "levantado": 0.0,
        "ratificado": 0.0,
        "aceptado": 0.0,
        "sin_decision": 0.0,
        "respondido_a_tiempo": 0.0,
        "respondido_tarde": 0.0,
        "perdido_por_vencimiento": 0.0,
        "sin_dato": {
            "levantadas_sin_valor": 0,
            "sin_fecha_vencimiento": 0,
            "sin_fecha_radicacion": 0,
        },
    }


def _inicio_del_mes(fecha: datetime) -> datetime:
    return fecha.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _mes_atras(fecha: datetime, meses: int) -> datetime:
    """El primer día del mes que está `meses` meses antes de `fecha`."""
    ini = _inicio_del_mes(fecha)
    for _ in range(meses):
        ini = _inicio_del_mes(ini - timedelta(days=1))
    return ini


def etiqueta_de_mes(clave: str) -> str:
    """'2026-08' → 'agosto 2026'. Para que el tablero se lea en español."""
    try:
        anio, mes = clave.split("-")
        return f"{_NOMBRE_MES[int(mes)]} {anio}"
    except Exception:
        return clave


def _sumar(casilla: dict, glosa, ahora: datetime) -> None:
    """Reparte UNA glosa en las casillas que le corresponden."""
    objetado = float(glosa.valor_objetado or 0.0)
    decision = (glosa.decision_eps or "").strip().upper()
    recuperado = float(glosa.valor_recuperado or 0.0)
    vence = a_utc(glosa.fecha_vencimiento)
    radicado = a_utc(glosa.radicado_en)

    casilla["glosas"] += 1
    casilla["glosado"] += objetado

    # ── En qué terminó con la EPS ──────────────────────────────────────
    if decision == "LEVANTADA":
        casilla["levantado"] += recuperado
        if recuperado <= 0:
            # La EPS nos dio la razón pero nadie anotó cuánta plata era.
            # No se supone que sea el objetado: se avisa que falta el dato.
            casilla["sin_dato"]["levantadas_sin_valor"] += 1
    elif decision == "RATIFICADA":
        casilla["ratificado"] += objetado
    elif decision == "ACEPTADA":
        casilla["aceptado"] += objetado
    else:
        casilla["sin_decision"] += objetado

    # ── Si se respondió, y si se respondió a tiempo ────────────────────
    if radicado is None:
        casilla["sin_dato"]["sin_fecha_radicacion"] += 1
    if vence is None:
        casilla["sin_dato"]["sin_fecha_vencimiento"] += 1

    if radicado is not None and vence is not None:
        if radicado <= vence:
            casilla["respondido_a_tiempo"] += objetado
        else:
            casilla["respondido_tarde"] += objetado
    elif radicado is None and vence is not None and vence < ahora and decision not in _DECIDIDAS:
        # Nunca se radicó, ya se venció y la EPS no decidió nada:
        # esa plata se perdió por no contestar a tiempo.
        casilla["perdido_por_vencimiento"] += objetado


def _redondear(casilla: dict) -> dict:
    """Deja los pesos en enteros — en cartera no se reportan centavos."""
    for clave, valor in casilla.items():
        if isinstance(valor, float):
            casilla[clave] = round(valor)
    return casilla


def _tasa(levantado: float, glosado: float) -> float:
    return round(100.0 * levantado / glosado, 2) if glosado else 0.0


def resumen_plata_recuperada(
    db: Session,
    meses: int = MESES_POR_DEFECTO,
    eps: str | None = None,
) -> dict:
    """El tablero completo: por mes, por EPS y el total del periodo.

    Una sola consulta a la base (no una por mes ni una por EPS): se traen las
    columnas necesarias del periodo y se reparten en memoria.
    """
    # Sin dato se usa el periodo por defecto; un número raro se acota,
    # no se cambia por el defecto a escondidas.
    try:
        pedidos = MESES_POR_DEFECTO if meses is None else int(meses)
    except (TypeError, ValueError):
        pedidos = MESES_POR_DEFECTO
    meses = max(1, min(pedidos, MESES_MAXIMO))
    ahora = ahora_utc()
    desde = _mes_atras(ahora, meses - 1)

    try:
        consulta = db.query(
            GlosaRecord.creado_en,
            GlosaRecord.eps,
            GlosaRecord.valor_objetado,
            GlosaRecord.valor_recuperado,
            GlosaRecord.decision_eps,
            GlosaRecord.fecha_vencimiento,
            GlosaRecord.radicado_en,
        ).filter(GlosaRecord.creado_en >= desde)
        if eps:
            consulta = consulta.filter(GlosaRecord.eps == eps)
        filas = consulta.all()
    except Exception as e:  # noqa: BLE001 — sin base, tablero vacío, no inventado
        logger.warning(f"[PLATA-RECUPERADA] no se pudo consultar: {e}")
        filas = []

    por_mes: dict[str, dict] = {}
    por_eps: dict[str, dict] = {}
    total = _casilla()

    for fila in filas:
        creado = a_utc(fila.creado_en) or ahora
        clave_mes = f"{creado.year:04d}-{creado.month:02d}"
        nombre_eps = (fila.eps or "SIN EPS").strip() or "SIN EPS"
        for casilla in (
            por_mes.setdefault(clave_mes, _casilla()),
            por_eps.setdefault(nombre_eps, _casilla()),
            total,
        ):
            _sumar(casilla, fila, ahora)

    meses_salida = []
    for clave in sorted(por_mes):
        casilla = _redondear(por_mes[clave])
        casilla["mes"] = clave
        casilla["etiqueta"] = etiqueta_de_mes(clave)
        casilla["tasa_levantado_pct"] = _tasa(casilla["levantado"], casilla["glosado"])
        meses_salida.append(casilla)

    eps_salida = []
    for nombre in por_eps:
        casilla = _redondear(por_eps[nombre])
        casilla["eps"] = nombre
        casilla["tasa_levantado_pct"] = _tasa(casilla["levantado"], casilla["glosado"])
        eps_salida.append(casilla)
    eps_salida.sort(key=lambda c: (-c["glosado"], c["eps"]))

    total = _redondear(total)
    total["tasa_levantado_pct"] = _tasa(total["levantado"], total["glosado"])

    return {
        "desde": desde.isoformat(),
        "hasta": ahora.isoformat(),
        "meses_pedidos": meses,
        "eps_filtrada": eps or "",
        "meses": meses_salida,
        "eps": eps_salida,
        "total": total,
        "nota": (
            "Cada cifra sale de una columna de la base. Lo que no tiene dato "
            "se cuenta aparte en «sin_dato» y no se rellena con supuestos."
        ),
    }
