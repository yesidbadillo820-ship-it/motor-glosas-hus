"""Qué modelo de Anthropic usa el motor, y qué acepta ese modelo.

**El defecto que esto corrige (10-09-2026).** El respaldo de IA estaba fijado
en `claude-sonnet-4-5`, un modelo de la generación anterior que además cuesta
MÁS que el actual: 3,00 / 15,00 dólares por millón de palabras contra 2,00 /
10,00 del Sonnet 5. Más viejo y más caro a la vez.

Hoy eso no se nota en la factura porque el motor principal es Groq y Anthropic
solo entra cuando Groq falla. Pero justamente por eso importa que el respaldo
funcione: es el que atiende el día malo.

**La trampa, y por qué esto no era cambiar un nombre.** La generación actual de
modelos (Sonnet 5, Opus 5, Opus 4.7 y 4.8, Fable) **rechaza el parámetro
`temperature` con error 400**. El motor se lo manda en las diez llamadas que
le hace a Anthropic. Cambiar solo el nombre del modelo habría convertido
«si Groq falla, responde Anthropic» en «si Groq falla, no responde nadie» —y
no se habría notado hasta el día que Groq fallara, que es el peor día para
enterarse.

Por eso el envío de `temperature` pasa a ser condicional en lugar de
desaparecer: con un modelo de la generación anterior (si alguien fija
`ANTHROPIC_MODEL` a mano) se sigue mandando exactamente como antes, y con uno
de la generación actual se omite. Ningún camino queda peor que hoy.
"""

from __future__ import annotations

# El respaldo por defecto. Más nuevo y más barato que el que había.
MODELO_POR_DEFECTO = "claude-sonnet-5"

# Familias que RECHAZAN `temperature` (y `top_p` / `top_k`) con error 400.
# Se comparan por comienzo del nombre para cubrir las variantes con fecha.
# Lista deliberadamente corta y explícita: lo que no esté acá se comporta
# como hasta hoy, que es lo seguro para un modelo que no conozcamos.
_FAMILIAS_QUE_RECHAZAN_MUESTREO: tuple[str, ...] = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-fable-5",
    "claude-mythos-5",
)


def acepta_temperature(modelo: str) -> bool:
    """¿Este modelo admite que le fijemos la `temperature`?

    Ojo con el parecido de los nombres: «claude-sonnet-4-5» (la generación
    anterior) SÍ la admite y «claude-sonnet-5» NO. Un `in` en vez de un
    `startswith` los confundiría.
    """
    m = (modelo or "").strip().lower()
    if not m:
        return True
    return not m.startswith(_FAMILIAS_QUE_RECHAZAN_MUESTREO)


def temperatura_si_aplica(modelo: str, valor: float) -> dict[str, float]:
    """El pedacito de cuerpo JSON con la `temperature`, o vacío.

    Se usa desplegándolo dentro del cuerpo de la petición:

        json={
            "model": modelo,
            "max_tokens": 3000,
            **temperatura_si_aplica(modelo, 0.10),
            ...
        }

    Así el sitio que llama no tiene que saberse qué modelo acepta qué, y
    agregar un modelo nuevo se hace en un solo lugar.
    """
    if valor is None or not acepta_temperature(modelo):
        return {}
    return {"temperature": valor}
