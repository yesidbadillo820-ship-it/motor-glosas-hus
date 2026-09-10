"""Cotejo de las fechas de atención: lo que dice el RIPS contra lo demás.

POR QUÉ EXISTE (08-09-2026, pedido de Yesid). Las fechas de ingreso y egreso
son la base de dos cosas caras: el plazo para radicar ante el ADRES y el
cobro de la estancia. Cuando el RIPS dice una cosa y la factura otra, la
cuenta se devuelve — y devolverla en pre-auditoría cuesta un oficio; que la
devuelva el ADRES cuesta la cuenta.

Este módulo compara y reporta. NO corrige nada y NO decide: entrega la lista
de lo que no cuadra para que el gestor mire y resuelva.

Cada hallazgo trae una gravedad, y la gravedad significa algo concreto:

  · GRAVE    — hay una contradicción imposible (un egreso anterior al
               ingreso, una factura emitida antes de que el paciente
               saliera). Alguien tiene que corregir un dato antes de
               radicar.
  · ADVIERTE — las fechas no coinciden con lo declarado, o falta un dato
               para poder verificar. Hay que mirarlo.
  · INFORMA  — no hay reparo; es contexto que le sirve al gestor.

REGLA DE LA CASA: lo que no se puede verificar se dice, no se supone. Si no
hay con qué comparar, sale un hallazgo que lo explica — nunca un «coincide»
que nadie comprobó.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from app.services.rips_fechas_atencion import FechasAtencion

GRAVE = "GRAVE"
ADVIERTE = "ADVIERTE"
INFORMA = "INFORMA"

# Diferencia que no vale la pena reportar. Las fuentes guardan unas con hora
# y otras sin ella, así que una diferencia dentro del mismo día es la misma
# fecha escrita de dos maneras, no una discrepancia.
TOLERANCIA_DIAS = 0


@dataclass(frozen=True)
class Hallazgo:
    codigo: str
    gravedad: str
    mensaje: str

    def a_dict(self) -> dict[str, str]:
        return {"codigo": self.codigo, "gravedad": self.gravedad, "mensaje": self.mensaje}


def _fecha(valor: Any) -> Optional[date]:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip().replace("T", " ").split(" ")[0]
    if not texto:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _dmy(f: date) -> str:
    return f.strftime("%d/%m/%Y")


def cotejar(
    fechas: Optional[FechasAtencion],
    *,
    ingreso_declarado: Any = None,
    egreso_declarado: Any = None,
    fecha_factura: Any = None,
    fecha_recibido: Any = None,
    tolerancia_dias: int = TOLERANCIA_DIAS,
) -> list[Hallazgo]:
    """Compara las fechas del RIPS con lo que se tenga a mano.

    `ingreso_declarado` / `egreso_declarado` son las fechas que el hospital
    dice tener (cuando existan). `fecha_factura` y `fecha_recibido` son las
    de la carátula y las del oficio: sirven para pillar imposibles aunque
    nadie haya declarado las de atención.
    """
    hallazgos: list[Hallazgo] = []

    if fechas is None:
        return [
            Hallazgo(
                "RIPS_NO_ENCONTRADO",
                ADVIERTE,
                "No se encontró el RIPS de esta factura: no se pudieron verificar "
                "las fechas de atención ni contar el plazo desde el egreso.",
            )
        ]

    if fechas.problema:
        hallazgos.append(
            Hallazgo(
                "RIPS_NO_LEIDO" if not fechas.completas else "RIPS_CON_REPAROS",
                ADVIERTE,
                f"El RIPS no se pudo aprovechar del todo: {fechas.problema}.",
            )
        )

    ingreso = _fecha(fechas.fecha_ingreso)
    egreso = _fecha(fechas.fecha_egreso)

    # ── 1. Coherencia interna del propio RIPS ───────────────────────────
    if ingreso and egreso and egreso < ingreso:
        hallazgos.append(
            Hallazgo(
                "EGRESO_ANTES_DEL_INGRESO",
                GRAVE,
                f"El RIPS trae el egreso ({_dmy(egreso)}) ANTES del ingreso "
                f"({_dmy(ingreso)}). Una de las dos fechas está mal.",
            )
        )

    # ── 2. Contra lo que declara el hospital ────────────────────────────
    for etiqueta, codigo, del_rips, declarado in (
        ("ingreso", "INGRESO_NO_COINCIDE", ingreso, _fecha(ingreso_declarado)),
        ("egreso", "EGRESO_NO_COINCIDE", egreso, _fecha(egreso_declarado)),
    ):
        if del_rips is None or declarado is None:
            continue
        diferencia = abs((del_rips - declarado).days)
        if diferencia > tolerancia_dias:
            hallazgos.append(
                Hallazgo(
                    codigo,
                    ADVIERTE,
                    f"La fecha de {etiqueta} no coincide: el RIPS dice "
                    f"{_dmy(del_rips)} y la factura {_dmy(declarado)} "
                    f"({diferencia} día{'s' if diferencia != 1 else ''} de diferencia).",
                )
            )

    # ── 3. Imposibles contra la factura y el oficio ─────────────────────
    f_factura = _fecha(fecha_factura)
    if egreso and f_factura and f_factura < egreso:
        hallazgos.append(
            Hallazgo(
                "FACTURA_ANTES_DEL_EGRESO",
                GRAVE,
                f"La factura es del {_dmy(f_factura)}, anterior al egreso del "
                f"{_dmy(egreso)}: no se puede facturar una atención que todavía "
                "no había terminado.",
            )
        )

    f_recibido = _fecha(fecha_recibido)
    if egreso and f_recibido and egreso > f_recibido:
        hallazgos.append(
            Hallazgo(
                "EGRESO_DESPUES_DE_RECIBIDA",
                GRAVE,
                f"El egreso del RIPS ({_dmy(egreso)}) es posterior al día en que "
                f"Facturación entregó la cuenta ({_dmy(f_recibido)}).",
            )
        )

    # ── 4. Lo que no se pudo verificar, dicho ───────────────────────────
    if egreso and egreso_declarado is None and ingreso_declarado is None:
        hallazgos.append(
            Hallazgo(
                "SIN_FECHAS_DECLARADAS",
                INFORMA,
                "El sistema no tiene fechas de ingreso y egreso declaradas por el "
                "hospital: se tomaron las del RIPS sin poder contrastarlas.",
            )
        )

    return hallazgos


def hay_reparos_graves(hallazgos: list[Hallazgo]) -> bool:
    return any(h.gravedad == GRAVE for h in hallazgos)
