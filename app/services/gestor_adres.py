"""Quién está trabajando cada factura del ADRES, cuando la macro no lo dice.

POR QUÉ EXISTE (02-09-2026). Yesid, con el Excel del paquete 31078 en la mano:
«la celda GESTOR no me dice qué gestor la está trabajando para esas que están
EN PROCESO o CERRADA; este dato se puede sacar por el correo de las celdas
Cerrada por».

La columna GESTOR sale de la macro que importa el paquete, y en estos
paquetes viene vacía: las 84 facturas decían «(sin gestor asignado)» aunque 16
estaban cerradas y 41 en proceso. El sistema sí sabe quién las trabaja, porque
guarda el correo de quien cierra la factura y de quien decide cada glosa. Aquí
se junta eso en una sola respuesta, con un orden claro y sin inventar:

  1. si la macro trae gestor, manda la macro;
  2. si la factura está CERRADA, es quien la cerró;
  3. si está EN PROCESO, es quien ha decidido sus glosas (la persona que más
     glosas decidió va primero; si son varias, se nombran todas);
  4. si la reabrieron y nadie ha decidido nada desde entonces, quien la reabrió;
  5. si no hay ninguna huella, sigue «(sin gestor asignado)».

Los correos se cambian por el nombre de la tabla de usuarios cuando existe;
si no existe, se deja el correo tal cual. Es lógica de negocio pura, sin base
de datos, para poder probarla con datos de mentira.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

SIN_GESTOR = "(sin gestor asignado)"
VENIA_EN_LA_MACRO = "(venía en la macro)"

ORIGEN_MACRO = "asignado en la macro"
ORIGEN_CIERRE = "quien la cerró"
ORIGEN_DECISIONES = "quien decidió sus glosas"
ORIGEN_REAPERTURA = "quien la reabrió"

MAXIMO_NOMBRES = 3


def nombre_de(correo: str | None, nombres: Mapping[str, str]) -> str:
    """El nombre del usuario si está en la tabla; si no, el correo tal cual."""
    limpio = (correo or "").strip()
    if not limpio:
        return ""
    return (nombres.get(limpio.lower()) or "").strip() or limpio


def quien_la_trabaja(
    gestor_macro: str | None,
    estado: str | None,
    cerrada_por: str | None,
    reabierta_por: str | None,
    decididos_por: Iterable[str | None],
    nombres: Mapping[str, str],
) -> tuple[str, str]:
    """(gestor que se muestra, de dónde salió). Nunca inventa: si no sabe, lo dice."""
    macro = (gestor_macro or "").strip()
    if macro and macro != SIN_GESTOR:
        return macro, ORIGEN_MACRO

    cierre = (cerrada_por or "").strip()
    if (estado or "").strip().upper() == "CERRADA" and cierre:
        return nombre_de(cierre, nombres), ORIGEN_CIERRE

    personas = Counter(
        nombre_de(p, nombres)
        for p in decididos_por
        if (p or "").strip() and (p or "").strip() != VENIA_EN_LA_MACRO
    )
    if personas:
        lista = [n for n, _ in personas.most_common()]
        texto = " / ".join(lista[:MAXIMO_NOMBRES])
        if len(lista) > MAXIMO_NOMBRES:
            texto += f" y {len(lista) - MAXIMO_NOMBRES} más"
        return texto, ORIGEN_DECISIONES

    reapertura = (reabierta_por or "").strip()
    if reapertura:
        return nombre_de(reapertura, nombres), ORIGEN_REAPERTURA
    if cierre:
        return nombre_de(cierre, nombres), ORIGEN_CIERRE
    return SIN_GESTOR, ""
