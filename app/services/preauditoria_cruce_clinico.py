"""El cruce clínico de la Pre-Auditoría Concurrente (V3, Pilar 2).

Único tramo de la cadena que le pregunta a un modelo de lenguaje, y el único
que puede tardar. Hace UNA sola pregunta, la que las reglas duras no pueden
contestar con una resta:

    ¿cada servicio facturado tiene respaldo en la epicrisis?

Tres candados, en este orden:

  1. **Reloj.** Se le entrega un presupuesto en segundos y no lo puede pasar.
     Vencido el plazo la llamada se corta y la respuesta sale sin ella.
  2. **Forma.** El modelo devuelve JSON o no devuelve nada: lo que no venga
     con la forma esperada se descarta en silencio.
  3. **Jerarquía.** Todo lo que salga de acá es ADVERTENCIA, nunca BLOQUEO.
     La IA levanta la mano; quien bloquea una factura es Python o una
     persona. Es la misma doctrina del motor de glosas.

Nunca levanta una excepción hacia arriba: una IA caída no puede impedir que
el hospital timbre. Devuelve lo que pudo y dice qué le pasó.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

from app.core.logging_utils import logger
from app.services.preauditoria_contrato import Alerta, CruceClinico, PayloadFactura
from app.services.preauditoria_reglas_duras import causal

URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"

# Cuánto se le presta al modelo, como mucho, aunque sobre presupuesto.
TOPE_IA_S = 6.0
# Por debajo de esto ni se intenta: alcanza para abrir la conexión y nada más.
MINIMO_IA_S = 1.5
# Cuántas líneas se le muestran. Una factura de UCI puede traer cientos de
# ítems; con las de mayor valor se juega el 90 % del riesgo y el prompt
# cabe en el presupuesto de tiempo.
MAX_ITEMS_AL_MODELO = 40
MAX_EPICRISIS = 6000

SYSTEM = (
    "Eres auditor médico de cuentas de un hospital público colombiano. Revisas una "
    "factura ANTES de que se timbre y dices qué servicios NO tienen respaldo en la "
    "epicrisis.\n"
    "REGLAS INNEGOCIABLES:\n"
    "1. Solo puedes usar lo que está escrito en la EPICRISIS y en la lista de ítems. "
    "PROHIBIDO suponer diagnósticos, procedimientos o antecedentes que no aparezcan.\n"
    "2. PROHIBIDO CITAR NÚMEROS DE ARTÍCULO, leyes, resoluciones o incisos: no se te "
    "entregó ninguna norma y cualquier número que escribas sería inventado.\n"
    "3. PROHIBIDO INVENTAR TARIFAS o valores. No opinas sobre precios.\n"
    "4. Si la epicrisis respalda el ítem, o si no tienes con qué decidir, NO lo "
    "reportes. Es preferible callar que levantar una alerta falsa: el facturador deja "
    "de creerle a la herramienta.\n"
    "5. Respondes ÚNICAMENTE con el JSON pedido, sin texto alrededor."
)

FORMATO = (
    '{"hallazgos":[{"item":"<cups o descripción tal como se te dio>",'
    '"motivo":"<por qué la epicrisis no lo respalda, en una frase>"}]}'
)


def _prompt(payload: PayloadFactura) -> str:
    items = sorted(payload.items, key=lambda i: i.total_efectivo(), reverse=True)
    lineas = []
    for item in items[:MAX_ITEMS_AL_MODELO]:
        lineas.append(
            f"- {item.etiqueta()} | {item.descripcion or 'sin descripción'} | "
            f"cantidad {item.cantidad:g}"
        )
    ocultos = len(items) - len(lineas)
    at = payload.atencion
    encabezado = [
        f"TIPO DE ATENCIÓN: {at.tipo or 'no informado'}",
        f"DIAGNÓSTICO PRINCIPAL: {at.diagnostico_principal or 'no informado'}",
    ]
    if at.diagnosticos:
        encabezado.append("OTROS DIAGNÓSTICOS: " + ", ".join(at.diagnosticos[:15]))
    if at.dias_estancia is not None:
        encabezado.append(f"DÍAS DE ESTANCIA: {at.dias_estancia}")
    if at.dias_uci:
        encabezado.append(f"DÍAS DE UCI: {at.dias_uci}")
    return (
        "\n".join(encabezado)
        + "\n\nEPICRISIS:\n"
        + (payload.epicrisis[:MAX_EPICRISIS] or "(el sistema no envió epicrisis)")
        + "\n\nÍTEMS FACTURADOS:\n"
        + "\n".join(lineas)
        + (f"\n(y {ocultos} ítem(s) más de menor valor, no listados)" if ocultos > 0 else "")
        + "\n\nDevuelve exactamente este JSON:\n"
        + FORMATO
    )


def _json_del_modelo(texto: str) -> dict[str, Any]:
    """Saca el JSON aunque el modelo lo haya envuelto en explicaciones."""
    crudo = (texto or "").strip()
    crudo = re.sub(r"^```(?:json)?|```$", "", crudo, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        return json.loads(crudo)
    except Exception:
        pass
    inicio, fin = crudo.find("{"), crudo.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            return json.loads(crudo[inicio : fin + 1])
        except Exception:
            pass
    return {}


def _a_alertas(datos: dict[str, Any], payload: PayloadFactura) -> list[Alerta]:
    """Convierte los hallazgos del modelo en alertas — descartando lo que no
    encaja. Un hallazgo sobre un ítem que no está en la factura es una
    alucinación y se tira sin contemplaciones."""
    por_etiqueta = {i.etiqueta().upper(): i for i in payload.items}
    alertas: list[Alerta] = []
    vistos: set[str] = set()
    for bruto in (datos.get("hallazgos") or [])[:MAX_ITEMS_AL_MODELO]:
        if not isinstance(bruto, dict):
            continue
        etiqueta = str(bruto.get("item") or "").strip()
        motivo = str(bruto.get("motivo") or "").strip()
        item = por_etiqueta.get(etiqueta.upper())
        if item is None or not motivo or etiqueta.upper() in vistos:
            continue
        vistos.add(etiqueta.upper())
        alertas.append(
            Alerta(
                codigo_glosa=causal(item, "CL"),
                titulo="Servicio sin respaldo visible en la epicrisis",
                detalle=(
                    f"{item.etiqueta()}: {motivo[:900]} — revisión asistida por IA sobre "
                    "la epicrisis enviada; la decisión de pertinencia es del médico "
                    "auditor."
                ),
                severidad="ADVERTENCIA",  # la IA nunca bloquea
                origen="IA",
                regla="cruce_clinico",
                item=item.etiqueta(),
                valor_en_riesgo=round(item.total_efectivo(), 2),
            )
        )
    return alertas


async def _llamar_groq(payload: PayloadFactura, presupuesto_s: float, modelo: str) -> str:
    import httpx

    clave = os.getenv("GROQ_API_KEY", "")
    # El techo de red va POR DEBAJO del presupuesto para que la respuesta
    # alcance a volver y a parsearse dentro del plazo.
    tope = max(1.0, presupuesto_s - 0.3)
    timeout = httpx.Timeout(connect=min(2.0, tope), read=tope, write=tope, pool=1.0)
    async with httpx.AsyncClient(timeout=timeout) as cliente:
        resp = await cliente.post(
            URL_GROQ,
            headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
            json={
                "model": modelo,
                "temperature": 0.0,
                "max_tokens": 900,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": _prompt(payload)},
                ],
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()["choices"][0]["message"]["content"]


def presupuesto_util(restante_s: float) -> float:
    """Cuánto tiempo se le puede prestar al modelo. 0 = no alcanza."""
    disponible = min(float(restante_s), TOPE_IA_S)
    return disponible if disponible >= MINIMO_IA_S else 0.0


async def cruzar_cups_contra_epicrisis(
    payload: PayloadFactura,
    presupuesto_s: float,
) -> tuple[list[Alerta], CruceClinico]:
    """Pregunta a la IA qué ítems no tienen respaldo clínico.

    Devuelve siempre: las alertas que hayan salido y el parte de cómo le fue.
    """
    from app.core.config import get_settings

    disponible = presupuesto_util(presupuesto_s)
    if disponible <= 0:
        return [], CruceClinico(
            estado="OMITIDO_POR_TIEMPO",
            detalle=(
                "Las reglas duras consumieron el presupuesto de tiempo; el cruce "
                "clínico no alcanzó a correr."
            ),
        )
    if not (payload.epicrisis or "").strip():
        # Sin texto clínico no hay nada que cruzar: el RIPS del HIS no trae
        # epicrisis ni notas (04-09-2026). Se omite LIMPIAMENTE, sin gastar
        # red y sin abortar: la factura ya se dictaminó con las reglas duras.
        return [], CruceClinico(
            estado="OMITIDO_SIN_NOTAS",
            detalle=(
                "El payload no trae notas clínicas ni epicrisis; el cruce clínico "
                "no tiene con qué trabajar."
            ),
        )
    if not os.getenv("GROQ_API_KEY", ""):
        return [], CruceClinico(
            estado="OMITIDO_SIN_IA",
            detalle="No hay GROQ_API_KEY configurada en el servidor.",
        )
    if not payload.items:
        return [], CruceClinico(estado="OMITIDO_SIN_IA", detalle="La factura no trae ítems.")

    modelo = getattr(get_settings(), "preauditoria_modelo", "llama-3.3-70b-versatile")
    arranque = time.monotonic()
    try:
        contenido = await asyncio.wait_for(
            _llamar_groq(payload, disponible, modelo), timeout=disponible
        )
    except (asyncio.TimeoutError, TimeoutError):
        return [], CruceClinico(
            estado="TIMEOUT",
            modelo_utilizado=modelo,
            duracion_ms=int((time.monotonic() - arranque) * 1000),
            detalle=(
                f"El cruce clínico no respondió dentro de los {disponible:.1f} s "
                "disponibles. La factura se dictaminó solo con las reglas duras."
            ),
        )
    except Exception as e:
        logger.warning(f"[PRE-AUDITORIA] cruce clínico falló: {e}")
        return [], CruceClinico(
            estado="ERROR",
            modelo_utilizado=modelo,
            duracion_ms=int((time.monotonic() - arranque) * 1000),
            detalle=f"El cruce clínico falló: {type(e).__name__}.",
        )

    alertas = _a_alertas(_json_del_modelo(contenido), payload)
    return alertas, CruceClinico(
        estado="OK",
        modelo_utilizado=modelo,
        duracion_ms=int((time.monotonic() - arranque) * 1000),
        detalle=f"{len(alertas)} ítem(s) sin respaldo visible en la epicrisis.",
    )
