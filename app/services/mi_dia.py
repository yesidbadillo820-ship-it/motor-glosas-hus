"""«Mi día» — las tres cosas que el gestor hace de verdad en el día.

Idea del 26-08-2026. Hay 32 pantallas para un gestor que, en el día a día,
hace tres cosas: responder lo que llegó, revisar lo que el motor marcó y
radicar lo que está listo. Las otras 32 siguen ahí para quien las necesite,
pero dejan de ser el punto de partida.

Las tres columnas
-----------------
  RESPONDER   llegó y todavía no tiene respuesta escrita
  REVISAR     el motor le puso un aviso, o pide soportes, o está en revisión
  RADICAR     ya está aprobada y solo falta subirla al portal

Una glosa cae en UNA sola columna. Se mira primero lo que ya está listo
(radicar), después lo que el motor marcó (revisar) y de último lo que falta
por responder: así lo que está a un paso de convertirse en plata no se
queda escondido debajo de un montón de trabajo por empezar.

El orden dentro de cada columna
-------------------------------
Primero lo que vence antes; a igualdad de días, lo de más plata. Es el orden
en que el gestor pierde dinero si no lo mira.
"""

from __future__ import annotations

import re

from app.core.tz import a_utc, ahora_utc

# Ya respondidas o cerradas: no son trabajo del día.
ESTADOS_CERRADOS = {"LEVANTADA", "ACEPTADA", "RATIFICADA", "CONCILIADA", "ARCHIVADA", "ANULADA"}
WORKFLOW_CERRADOS = {"RESPONDIDA", "CONCILIADA", "LEVANTADA"}

# Los avisos que el motor deja pegados al dictamen cuando algo no cuadra.
# Son los mismos que el auditor ve resaltados en pantalla y en el papel.
_PAT_AVISO = re.compile(
    r"(⚠|AVISO DEL MOTOR|ANTES DE RADICAR|NO RADIQUE|FALTA EL SOPORTE|REVISAR ANTES DE RADICAR)",
    re.IGNORECASE,
)


def _cerrada(glosa) -> bool:
    estado = (getattr(glosa, "estado", None) or "").strip().upper()
    workflow = (getattr(glosa, "workflow_state", None) or "").strip().upper()
    return estado in ESTADOS_CERRADOS or workflow in WORKFLOW_CERRADOS


def tiene_aviso_del_motor(dictamen: str | None) -> bool:
    """¿El motor le dejó un aviso pegado al dictamen?"""
    return bool(dictamen) and bool(_PAT_AVISO.search(dictamen))


def _columna(glosa) -> str:
    """En cuál de las tres cosas del día cae esta glosa."""
    estado = (getattr(glosa, "estado", None) or "").strip().upper()
    workflow = (getattr(glosa, "workflow_state", None) or "").strip().upper()
    dictamen = getattr(glosa, "dictamen", None)

    # Ya está aprobada y sin radicar: es lo más cerca de volverse plata.
    if workflow == "APROBADA" and not getattr(glosa, "radicado_en", None):
        return "radicar"
    # El motor la marcó, o pide soportes, o alguien la dejó en revisión.
    if estado == "REQUIERE_SOPORTES" or workflow == "EN_REVISION":
        return "revisar"
    if tiene_aviso_del_motor(dictamen):
        return "revisar"
    # Tiene dictamen escrito pero nadie lo ha aprobado todavía.
    if dictamen:
        return "revisar"
    return "responder"


def _motivo(glosa, columna: str) -> str:
    """En una línea, por qué está en esa columna. Sin tecnicismos."""
    estado = (getattr(glosa, "estado", None) or "").strip().upper()
    workflow = (getattr(glosa, "workflow_state", None) or "").strip().upper()
    if columna == "radicar":
        return "Aprobada — solo falta subirla al portal"
    if columna == "revisar":
        if estado == "REQUIERE_SOPORTES":
            return "Pide soportes"
        if tiene_aviso_del_motor(getattr(glosa, "dictamen", None)):
            return "El motor le dejó un aviso"
        if workflow == "EN_REVISION":
            return "En revisión"
        return "Tiene respuesta escrita, falta aprobarla"
    return "Sin respuesta escrita"


def _dias_que_faltan(glosa, ahora) -> tuple[int | None, bool]:
    """Días hasta el vencimiento y si salieron de una fecha o del contador.

    Manda la fecha de vencimiento. Cuando no hay fecha se usa el contador
    `dias_restantes`, que el importador sí calcula para las glosas escritas a
    mano en el motor.

    OJO CON EL CERO — la trampa que casi se cuela:
    la columna `dias_restantes` vale 0 por defecto. Un 0 sin fecha de
    vencimiento puede ser dos cosas distintas y en la base se ven idénticas:
    «se venció» o «nadie le calculó el plazo». No hay forma de distinguirlas,
    así que no se escoge ninguna: se devuelve «no se sabe» y esa glosa se va
    al final, en vez de disfrazarse de urgente y empujar hacia abajo lo que
    de verdad vence mañana. Cualquier otro número del contador sí es una
    cuenta que alguien hizo, y se usa.

    Devuelve (días, viene_del_contador). `días` en None = no se sabe.
    """
    vence = a_utc(getattr(glosa, "fecha_vencimiento", None))
    if vence is not None:
        return (vence - ahora).days, False
    dias = getattr(glosa, "dias_restantes", None)
    if dias is None or int(dias) == 0:
        return None, False
    return int(dias), True


def _ficha(glosa, columna: str, ahora) -> dict:
    dias, del_contador = _dias_que_faltan(glosa, ahora)
    return {
        "id": getattr(glosa, "id", None),
        "factura": getattr(glosa, "factura", "") or "",
        "eps": getattr(glosa, "eps", "") or "",
        "codigo_glosa": getattr(glosa, "codigo_glosa", "") or "",
        "valor_objetado": round(float(getattr(glosa, "valor_objetado", 0) or 0)),
        "dias_que_faltan": dias,
        "plazo_sin_fecha": del_contador,
        "vencida": dias is not None and dias < 0,
        "motivo": _motivo(glosa, columna),
    }


def _orden(ficha: dict) -> tuple:
    """Primero lo que vence antes; a igualdad de días, lo de más plata.

    Lo que no tiene plazo conocido va al final: no se le inventa uno.
    """
    dias = ficha["dias_que_faltan"]
    sin_plazo = 1 if dias is None else 0
    return (sin_plazo, dias if dias is not None else 0, -ficha["valor_objetado"])


def armar_mi_dia(glosas, limite_por_columna: int = 25) -> dict:
    """Reparte las glosas del gestor en las tres cosas que hace en el día."""
    ahora = ahora_utc()
    columnas: dict[str, list[dict]] = {"responder": [], "revisar": [], "radicar": []}

    for glosa in glosas or []:
        if _cerrada(glosa):
            continue
        columna = _columna(glosa)
        columnas[columna].append(_ficha(glosa, columna, ahora))

    salida = {}
    for nombre, fichas in columnas.items():
        fichas.sort(key=_orden)
        salida[nombre] = {
            "cantidad": len(fichas),
            "valor": sum(f["valor_objetado"] for f in fichas),
            "vencidas": sum(1 for f in fichas if f["vencida"]),
            "glosas": fichas[:limite_por_columna],
            "hay_mas": max(0, len(fichas) - limite_por_columna),
        }

    total_abiertas = sum(c["cantidad"] for c in salida.values())
    return {
        "generado_en": ahora.isoformat(),
        "responder": salida["responder"],
        "revisar": salida["revisar"],
        "radicar": salida["radicar"],
        "total_abiertas": total_abiertas,
        "valor_en_riesgo": sum(c["valor"] for c in salida.values()),
        "vencidas": sum(c["vencidas"] for c in salida.values()),
    }
