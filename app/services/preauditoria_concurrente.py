"""El motor de la Pre-Auditoría Concurrente (V3, Pilar 2).

Acá se arma la cadena completa y se cuida el reloj. El HIS del hospital nos
consulta ANTES de timbrar una factura y espera una respuesta mientras el
facturador mira la pantalla: el compromiso es **10 segundos como techo duro**
(el facturador tolera 15; los 5 que sobran son margen de red, no nuestros).

    payload del HIS
        → reglas duras (Python, deterministas)   ~0,1 s
        → cruce clínico (Groq, con reloj)        ≤ 6 s
        → dictamen + fila en pre_auditoria_eventos

Tres decisiones que conviene tener presentes al leer el código:

1. **El reloj manda sobre la calidad.** Si las reglas duras se demoraron, el
   cruce clínico se recorta o no corre. Nunca al revés.
2. **Una IA caída no bloquea al hospital.** Si el cruce clínico falla o se
   vence, la factura se dictamina igual con las reglas duras — y la respuesta
   lo dice, para que nadie confunda «no encontramos nada» con «no miramos».
3. **Queda escrito siempre.** Si la fila del evento no se puede guardar, la
   respuesta sale igual: el facturador no puede quedarse esperando porque la
   base de datos tuvo un mal momento.

Arquitectura: docs/ARQUITECTURA_V3_PILAR2_PREAUDITORIA.md
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.models.db import (
    PA_ADVERTENCIA,
    PA_APROBADO,
    PA_BLOQUEO,
    PreAuditoriaEventoRecord,
)
from app.services.preauditoria_contrato import (
    Alerta,
    CruceClinico,
    PayloadFactura,
    RespuestaPreAuditoria,
    accion_de,
    consolidar_valor_en_riesgo,
    estado_de,
)
from app.services.preauditoria_cruce_clinico import cruzar_cups_contra_epicrisis
from app.services.preauditoria_reglas_duras import Contexto, correr_reglas_duras

# El techo duro. Lo prometido al HIS, no una aspiración.
PRESUPUESTO_TOTAL_S = 10.0
# Lo que se aparta para escribir la fila del evento y serializar la respuesta.
RESERVA_ESCRITURA_S = 0.5


# Una factura cuenta como CORREGIDA cuando, después de un BLOQUEO, el HIS la
# vuelve a mandar y esa vez pasa. Es la única señal honesta que tenemos: el
# motor no ve la caja, así que no puede afirmar que alguien acató nada si la
# factura nunca volvió.
ESTADOS_QUE_PASAN = (PA_APROBADO, PA_ADVERTENCIA)


def resumen(db: Session, limite_facturas: int = 5000) -> dict:
    """Las cifras del tablero de pre-auditoría.

    **Dinero salvado** es la suma del `valor_en_riesgo` de las facturas que
    fueron BLOQUEADAS y después volvieron a evaluarse sin bloqueo: se
    corrigieron antes de timbrar, y esa plata no entró a cartera.

    Lo que NO se cuenta como salvado: una factura bloqueada que nunca volvió.
    No sabemos si la corrigieron, si la timbraron igual o si la dejaron
    quieta — y decir «salvamos» sin saberlo sería inventar una cifra que
    después nadie puede sostener ante gerencia. Esa plata va aparte, en
    `riesgo_sin_resolver`.

    Una sola consulta ordenada y un recorrido en memoria: nada de una
    consulta por factura.
    """
    filas = (
        db.query(
            PreAuditoriaEventoRecord.factura,
            PreAuditoriaEventoRecord.estado,
            PreAuditoriaEventoRecord.valor_en_riesgo,
            PreAuditoriaEventoRecord.creado_en,
        )
        .order_by(PreAuditoriaEventoRecord.id.asc())
        .limit(limite_facturas)
        .all()
    )

    por_estado: dict[str, int] = {}
    # Por factura: el mayor riesgo bloqueado y si después pasó.
    bloqueado: dict[str, float] = {}
    paso_despues: dict[str, bool] = {}

    for factura, estado, riesgo, _creado in filas:
        estado = estado or ""
        por_estado[estado] = por_estado.get(estado, 0) + 1
        clave = (factura or "").strip()
        if not clave:
            continue
        if estado == PA_BLOQUEO:
            bloqueado[clave] = max(bloqueado.get(clave, 0.0), float(riesgo or 0.0))
            paso_despues[clave] = False
        elif estado in ESTADOS_QUE_PASAN and clave in bloqueado:
            paso_despues[clave] = True

    salvado = round(sum(v for k, v in bloqueado.items() if paso_despues.get(k)), 2)
    sin_resolver = round(sum(v for k, v in bloqueado.items() if not paso_despues.get(k)), 2)

    return {
        "evaluaciones": len(filas),
        "por_estado": por_estado,
        "facturas_bloqueadas": len(bloqueado),
        "facturas_corregidas": sum(1 for k in bloqueado if paso_despues.get(k)),
        "dinero_salvado": salvado,
        "riesgo_sin_resolver": sin_resolver,
    }


def huella_de(payload: PayloadFactura) -> str:
    """Huella del payload: mismo contenido → misma huella.

    Sirve para ver que el HIS reintentó la misma factura sin cambiar nada
    (y para repetir una evaluación sobre datos idénticos el día que una
    regla resulte equivocada).
    """
    crudo = payload.model_dump_json(exclude_none=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _alerta_de_cruce_incompleto(cruce: CruceClinico) -> Optional[Alerta]:
    """Cuando la IA estaba disponible y aun así no revisó ESTA factura.

    La distinción importa y es deliberada:

      · Si el servidor no tiene IA configurada (OMITIDO_SIN_IA), eso es un
        estado del despliegue, no un riesgo de esta factura: no se levanta
        alerta —se avisaría en todas, y una advertencia que sale siempre
        deja de leerse—. Queda en el campo `cruce_clinico` de la respuesta.
      · Lo mismo si el payload no trae notas clínicas (OMITIDO_SIN_NOTAS):
        el RIPS del HIS nunca las trae, y avisar en cada factura sería
        ruido. Queda en `cruce_clinico` y en `omisiones`.
      · Si la IA existía y esta factura específica se quedó sin revisar
        (TIMEOUT, ERROR o sin tiempo), SÍ se avisa: esta cuenta recibió
        menos revisión que las demás y el facturador tiene derecho a saberlo.
    """
    if cruce.estado in ("OK", "OMITIDO_SIN_IA", "OMITIDO_SIN_NOTAS"):
        return None
    return Alerta(
        codigo_glosa="",
        titulo="El cruce clínico no alcanzó a revisar esta factura",
        detalle=(cruce.detalle or "El cruce clínico no pudo completarse.")
        + " Los reparos de tarifa, cantidades, fechas, género y edad SÍ se revisaron.",
        severidad="ADVERTENCIA",
        origen="REGLA_DURA",
        regla="cruce_clinico_incompleto",
        valor_en_riesgo=0.0,
    )


def _guardar_evento(
    db: Session,
    payload: PayloadFactura,
    respuesta: RespuestaPreAuditoria,
    duracion_reglas_ms: int,
    actor: str,
) -> Optional[int]:
    """Escribe la fila del libro. Si falla, la respuesta sale igual."""
    try:
        fila = PreAuditoriaEventoRecord(
            factura=(payload.factura or "")[:50],
            eps=(payload.eps or "")[:200],
            huella_payload=huella_de(payload),
            estado=respuesta.status,
            recomendacion_accion=respuesta.recomendacion_accion,
            valor_en_riesgo=respuesta.valor_en_riesgo,
            valor_factura=respuesta.valor_factura,
            total_alertas=len(respuesta.alertas),
            payload_base=payload.model_dump_json(),
            alertas=json.dumps([a.model_dump() for a in respuesta.alertas], ensure_ascii=False),
            cruce_clinico_estado=respuesta.cruce_clinico.estado,
            modelo_utilizado=respuesta.cruce_clinico.modelo_utilizado or "",
            duracion_ms=respuesta.duracion_ms,
            duracion_reglas_ms=duracion_reglas_ms,
            duracion_ia_ms=respuesta.cruce_clinico.duracion_ms,
            actor=(actor or "")[:120],
        )
        db.add(fila)
        db.commit()
        db.refresh(fila)
        return int(fila.id)
    except Exception as e:  # pragma: no cover - defensa
        logger.error(f"[PRE-AUDITORIA] no se pudo guardar el evento: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


async def evaluar(
    db: Session,
    payload: PayloadFactura,
    actor: str = "his",
    ahora: Optional[datetime] = None,
    omisiones: Optional[list[str]] = None,
) -> RespuestaPreAuditoria:
    """Evalúa una factura antes de timbrarla y deja constancia.

    Las reglas duras corren en el mismo hilo a propósito: son cuentas de
    milisegundos y comparten la sesión de SQLAlchemy, que no es de hilos.
    Lo que sí es asíncrono es el único tramo que espera por la red.
    """
    arranque = time.monotonic()

    reglas_arranque = time.monotonic()
    alertas = correr_reglas_duras(payload, Contexto(db=db, ahora=ahora or datetime.now()))
    duracion_reglas_ms = int((time.monotonic() - reglas_arranque) * 1000)

    restante = PRESUPUESTO_TOTAL_S - (time.monotonic() - arranque) - RESERVA_ESCRITURA_S
    alertas_ia, cruce = await cruzar_cups_contra_epicrisis(payload, restante)
    alertas.extend(alertas_ia)

    aviso = _alerta_de_cruce_incompleto(cruce)
    if aviso is not None:
        alertas.append(aviso)

    valor_factura = round(payload.total_efectivo(), 2)
    estado = estado_de(alertas)
    respuesta = RespuestaPreAuditoria(
        status=estado,  # type: ignore[arg-type]
        alertas=alertas,
        valor_en_riesgo=consolidar_valor_en_riesgo(alertas, valor_factura),
        recomendacion_accion=accion_de(estado),  # type: ignore[arg-type]
        factura=payload.factura,
        eps=payload.eps,
        valor_factura=valor_factura,
        duracion_ms=int((time.monotonic() - arranque) * 1000),
        cruce_clinico=cruce,
        omisiones=list(omisiones or []),
    )
    respuesta.evento_id = _guardar_evento(db, payload, respuesta, duracion_reglas_ms, actor)
    return respuesta
