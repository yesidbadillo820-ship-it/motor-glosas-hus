"""Dibujar una vela en la consola, a partir de sus cuatro números.

Existe para responder a una duda razonable: «el CSV son solo datos, no dice
nada de velas». Sí lo dice — **una vela japonesa ES esos cuatro números**:

- el **cuerpo** va de la apertura al cierre;
- **hueco o lleno** según el cierre haya quedado arriba o abajo de la apertura;
- la **mecha de arriba** va de lo alto del cuerpo hasta el máximo;
- la **mecha de abajo**, de lo bajo del cuerpo hasta el mínimo.

TradingView dibuja exactamente eso. El gráfico no añade ni un dato que no esté
en el archivo: es la misma información, pintada.
"""

from __future__ import annotations

from .dominio import Vela

#: Cuántas filas de texto tiene el dibujo. Impar, para que el cuerpo quede
#: centrado cuando la vela es simétrica.
ALTO = 15


def _fila(precio_alto: float, precio_bajo: float, alto: int, precio: float) -> int:
    """En qué fila del dibujo cae un precio (0 = arriba del todo)."""
    if precio_alto == precio_bajo:
        return alto // 2
    proporcion = (precio_alto - precio) / (precio_alto - precio_bajo)
    return min(alto - 1, max(0, round(proporcion * (alto - 1))))


def en_texto(vela: Vela, alto: int = ALTO, decimales: int = 5) -> str:
    """La vela dibujada, con cada número señalado donde le corresponde."""
    fila = lambda p: _fila(vela.maximo, vela.minimo, alto, p)  # noqa: E731
    f_max, f_min = fila(vela.maximo), fila(vela.minimo)
    f_cima, f_base = fila(vela.cima_cuerpo), fila(vela.base_cuerpo)

    # Hueca si cerró subiendo, llena si cerró bajando: la forma original
    # japonesa, y la que se lee igual sin distinguir el rojo del verde.
    relleno = " " if vela.alcista else "█"
    num = lambda p: f"{p:,.{decimales}f}"  # noqa: E731

    etiquetas = {
        f_max: f"máximo   {num(vela.maximo)}",
        f_cima: f"{'cierre  ' if vela.alcista else 'apertura'} {num(vela.cima_cuerpo)}",
        f_base: f"{'apertura' if vela.alcista else 'cierre  '} {num(vela.base_cuerpo)}",
        f_min: f"mínimo   {num(vela.minimo)}",
    }

    lineas = []
    for f in range(alto):
        if f < f_cima or f > f_base:
            dibujo = "   │   "
        elif f == f_cima:
            dibujo = "  ┌─┐  " if f_cima != f_base else "  ┝━┥  "
        elif f == f_base:
            dibujo = "  └─┘  "
        else:
            dibujo = f"  │{relleno}│  "
        etiqueta = etiquetas.get(f, "")
        lineas.append(f"{dibujo}{'  ← ' + etiqueta if etiqueta else ''}".rstrip())

    return "\n".join(lineas)


def medidas(vela: Vela, decimales: int = 5) -> list[str]:
    """Las cuentas del libro sobre esta vela, ya hechas."""

    def n(x: float) -> str:
        return f"{x:,.{decimales}f}"

    def veces(parte: float) -> str:
        if vela.cuerpo <= 0:
            return "— (no tiene cuerpo)"
        return f"{parte / vela.cuerpo:.1f} veces el cuerpo"

    return [
        f"color          {vela.color} ({'cerró subiendo' if vela.alcista else 'cerró bajando'})",
        f"cuerpo         {n(vela.cuerpo)}",
        f"mecha superior {n(vela.mecha_superior)}   {veces(vela.mecha_superior)}",
        f"mecha inferior {n(vela.mecha_inferior)}   {veces(vela.mecha_inferior)}",
        f"rango total    {n(vela.rango)}",
    ]
