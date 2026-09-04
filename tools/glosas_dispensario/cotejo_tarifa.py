"""Cotejo del valor realmente facturado contra la tarifa pactada del contrato.

Responde la pregunta del auditor: **¿de verdad se está cobrando de más?** Y si
la respuesta es sí, cuánto exactamente, para poder aceptar la glosa por ese
valor y no por el que diga la EPS.

Los tres números del cotejo:

    valor facturado   el que se leyó en el PDF de la factura (la línea del
                      servicio glosado). Si no se pudo leer, NO hay cotejo.
    tarifa pactada    la del anexo tarifario del contrato 440-DIGSA-DMBUG-2025.
                      Si el código no está pactado, NO hay cotejo.
    valor objetado    lo que la EPS descontó en la glosa.

Los veredictos posibles:

    SIN COTEJO                    falta el PDF o falta la tarifa → decide el auditor.
    COBRO A TARIFA                facturado = pactado → la glosa es infundada.
    COBRO POR DEBAJO              facturado < pactado → la glosa es infundada.
    MAYOR VALOR VERIFICADO        facturado > pactado en un caso aislado → SÍ hay
                                  sobrecobro: se sugiere aceptar la diferencia.
    MAYOR VALOR POR VIGENCIA      facturado > pactado, pero la MISMA diferencia
                                  porcentual se repite en el lote: eso no es un
                                  error de cobro, es la actualización de tarifas
                                  del año (parágrafos 3 y 4 del contrato). No se
                                  sugiere aceptar: se sustenta con la resolución.

REGLA DURA: la sugerencia de aceptar solo nace de dos cifras verificadas —la
leída del PDF y la pactada en el anexo—. Sin las dos no se sugiere nada, y el
bot NUNCA escribe el valor aceptado en el Excel del cargue: la columna es para
que el auditor decida.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _dinero import a_texto  # noqa: E402  (el UNICO lector/escritor de pesos de tools/)

# Diferencias de uno o dos pesos son el redondeo del anexo (trae centavos),
# no un cobro de más.
TOLERANCIA_PESOS = 2
# A partir de cuántas líneas con la misma diferencia porcentual se considera
# que el lote entero viene de una actualización de tarifas y no de un error.
MINIMO_LINEAS_FACTOR = 3
# Redondeo del factor para agruparlo (1.0700 y 1.0697 son el mismo aumento).
DECIMALES_FACTOR = 3

SIN_COTEJO = "SIN COTEJO"
A_TARIFA = "COBRO A TARIFA"
POR_DEBAJO = "COBRO POR DEBAJO DE LO PACTADO"
SOBRECOBRO = "MAYOR VALOR VERIFICADO"
POR_VIGENCIA = "MAYOR VALOR POR VIGENCIA"


def elegir_valor_facturado(
    importes: list[int] | None, tarifa: int | None
) -> tuple[int | None, str]:
    """De los importes que trae la línea del PDF, cuál es el valor unitario.

    Una línea de factura suele traer cantidad, valor unitario y valor total.
    Comparar contra la tarifa el número equivocado es justo el error que haría
    ver un sobrecobro donde no lo hay, así que:

      - si un importe coincide con la tarifa pactada, ese es el unitario;
      - si el mayor importe es un múltiplo exacto del menor, el menor es el
        unitario y el múltiplo es la cantidad;
      - si la línea trae un solo importe, ese es;
      - si nada de lo anterior aclara cuál es, NO se elige ninguno: se deja el
        caso para revisión manual antes que arriesgar una cifra equivocada.
    """
    valores = sorted({int(v) for v in (importes or []) if v})
    if not valores:
        return None, "no se leyó ningún valor en la línea del servicio"
    if tarifa:
        for v in valores:
            if abs(v - tarifa) <= TOLERANCIA_PESOS:
                return v, ""
    if len(valores) == 1:
        return valores[0], ""
    menor, mayor = valores[0], valores[-1]
    if menor > 0:
        veces = round(mayor / menor)
        if veces >= 2 and abs(mayor - veces * menor) <= TOLERANCIA_PESOS:
            return menor, ""
    return None, (
        f"la línea trae varios valores ({', '.join(a_texto(v) for v in valores)}) y no se "
        "puede afirmar cuál es el unitario"
    )


def factor(valor_facturado: int | None, tarifa: int | None) -> float | None:
    """Cuántas veces la tarifa pactada cabe en lo facturado (1,07 = 7% más)."""
    if not valor_facturado or not tarifa or tarifa <= 0:
        return None
    return round(valor_facturado / tarifa, DECIMALES_FACTOR)


def factores_repetidos(lineas: list[tuple[int | None, int | None]]) -> set[float]:
    """Los factores que se repiten en el lote: son actualización de tarifas.

    `lineas` son pares (valor facturado, tarifa pactada) de todo el lote. Un
    mismo porcentaje de diferencia en varias facturas distintas no es un error
    de cobro puntual; es el aumento del año aplicado a toda la facturación.
    """
    cuenta = Counter()
    for facturado, tarifa in lineas:
        f = factor(facturado, tarifa)
        if f and f > 1:
            cuenta[f] += 1
    return {f for f, n in cuenta.items() if n >= MINIMO_LINEAS_FACTOR}


def cotejar(
    valor_facturado: int | None,
    tarifa: dict | None,
    valor_objetado: int | None,
    cups: str = "",
    factores_del_lote: set[float] | None = None,
    motivo_sin_lectura: str = "",
) -> dict:
    """El cotejo de una línea glosada. Devuelve el veredicto, la diferencia,
    cuánto se sugiere aceptar y el texto de la respuesta sugerida.

    `tarifa` es el registro del tarifario ({precio, descripcion, fuente}).
    `factores_del_lote` son los factores repetidos que calculó
    `factores_repetidos` para todo el lote (si se omite, no se distingue la
    actualización de vigencia y toda diferencia se reporta como sobrecobro)."""
    precio = (tarifa or {}).get("precio")
    objetado = int(valor_objetado or 0)
    if not valor_facturado:
        falta = motivo_sin_lectura or "no se pudo leer el valor facturado en el PDF de la factura"
    else:
        falta = f"el código {cups} no aparece en el anexo tarifario del contrato"
    base = dict(
        veredicto=SIN_COTEJO,
        valor_facturado=valor_facturado or None,
        tarifa=precio or None,
        diferencia=None,
        porcentaje=None,
        aceptar=0,
        # Lo que se pide levantar cuando la aceptación es parcial. Lo calcula
        # el cotejo y no la redacción, para que el texto de la respuesta y las
        # columnas del Excel no puedan decir cifras distintas.
        resto=0,
        respuesta=f"SIN COTEJO: {falta}. Revisar a mano antes de decidir.",
    )
    if not valor_facturado or not precio:
        return base

    diferencia = valor_facturado - precio
    f = factor(valor_facturado, precio)
    base.update(diferencia=diferencia, porcentaje=round((f - 1) * 100, 1) if f else None)

    if abs(diferencia) <= TOLERANCIA_PESOS:
        base.update(
            veredicto=A_TARIFA,
            respuesta=(
                f"NO ACEPTAR: el valor facturado ({a_texto(valor_facturado)}) es exactamente "
                f"la tarifa pactada para el código {cups}. La glosa por mayor valor cobrado "
                "es infundada."
            ),
        )
        return base

    if diferencia < 0:
        base.update(
            veredicto=POR_DEBAJO,
            respuesta=(
                f"NO ACEPTAR: el valor facturado ({a_texto(valor_facturado)}) es INFERIOR a la "
                f"tarifa pactada ({a_texto(precio)}) para el código {cups}. No hay mayor valor "
                "cobrado."
            ),
        )
        return base

    # Hay diferencia a favor de la EPS. Solo se puede aceptar hasta lo objetado.
    aceptable = min(diferencia, objetado) if objetado else diferencia
    detalle_cifras = (
        f"valor facturado {a_texto(valor_facturado)} contra tarifa pactada {a_texto(precio)} "
        f"del código {cups} (+{base['porcentaje']}%)"
    )

    if factores_del_lote and f in factores_del_lote:
        base.update(
            veredicto=POR_VIGENCIA,
            aceptar=0,
            respuesta=(
                f"NO ACEPTAR AUTOMÁTICAMENTE: la diferencia de {a_texto(diferencia)} "
                f"({detalle_cifras}) se repite igual en otras facturas del lote, así que "
                "corresponde a la actualización de tarifas del año y no a un cobro de más. "
                "Sustentar con la resolución de tarifas vigente y el modificatorio previsto "
                "en los parágrafos 3 y 4 del contrato 440-DIGSA-DMBUG-2025. Solo si no "
                f"existen esos documentos procedería aceptar {a_texto(aceptable)}."
            ),
        )
        return base

    if objetado and diferencia >= objetado:
        respuesta = (
            f"SE ACEPTA LA GLOSA POR {a_texto(objetado)} POR MAYOR VALOR COBRADO: "
            f"{detalle_cifras}. La diferencia verificada ({a_texto(diferencia)}) cubre el "
            "valor objetado."
        )
    elif objetado:
        resto = objetado - diferencia
        respuesta = (
            f"SE ACEPTA PARCIALMENTE LA GLOSA POR {a_texto(diferencia)} POR MAYOR VALOR "
            f"COBRADO ({detalle_cifras}) Y SE SOLICITA EL LEVANTAMIENTO DE LOS "
            f"{a_texto(resto)} RESTANTES, POR CORRESPONDER A VALOR PACTADO EN EL CONTRATO."
        )
    else:
        respuesta = (
            f"MAYOR VALOR COBRADO VERIFICADO POR {a_texto(diferencia)} ({detalle_cifras}). "
            "Sin valor objetado en el detalle: definir con el auditor cuánto aceptar."
        )
    base.update(
        veredicto=SOBRECOBRO,
        aceptar=aceptable,
        resto=max(0, objetado - aceptable) if objetado else 0,
        respuesta=respuesta,
    )
    return base
