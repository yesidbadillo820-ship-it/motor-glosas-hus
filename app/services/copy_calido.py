"""Copy cálido — micro-textos con calidez humana para la "Capa de Vida".

Módulo PURO (sin BD ni IO): frases de saludo, celebración y ánimo que la
UI muestra para que el motor deje de sentirse una máquina expendedora. La
selección de frase es DETERMINISTA dado un índice (rota por día/contador),
así los tests son estables y no dependen de random.

Todo es aditivo: nada de esto cambia el dictamen ni la lógica del motor.
"""

from __future__ import annotations

# ── Saludo por franja horaria (hora de Bogotá) ───────────────────────────
_SALUDO_MADRUGADA = "Trabajando temprano"
_SALUDO_MANANA = "Buenos días"
_SALUDO_TARDE = "Buenas tardes"
_SALUDO_NOCHE = "Buenas noches"


def saludo_por_hora(hora_bogota: int) -> str:
    """Devuelve el saludo según la hora local (0-23) de Bogotá."""
    h = hora_bogota % 24
    if 5 <= h < 12:
        return _SALUDO_MANANA
    if 12 <= h < 19:
        return _SALUDO_TARDE
    if 19 <= h < 24:
        return _SALUDO_NOCHE
    return _SALUDO_MADRUGADA


# ── Frases de ánimo (rotan por día) ──────────────────────────────────────
_FRASES_ANIMO = (
    "Cada glosa bien respondida es plata que vuelve al hospital.",
    "Vamos con toda: hoy es un buen día para levantar glosas.",
    "Tu trabajo defiende la cartera de la ESE, factura por factura.",
    "Un dictamen sólido hoy es un pago asegurado mañana.",
    "Paso a paso: cada respuesta cuenta.",
    "El contrato y los soportes están de tu lado. A por ellas.",
    "Que las EPS no se queden con lo que es del hospital.",
)


def frase_animo(indice: int) -> str:
    """Frase de ánimo rotativa y estable dado un índice (ej. día del año)."""
    return _FRASES_ANIMO[indice % len(_FRASES_ANIMO)]


# ── Celebraciones (según el hito) ────────────────────────────────────────
def celebrar_levantada(eps: str, valor: float) -> str:
    """Mensaje cuando una glosa se levanta (la IPS gana)."""
    eps = (eps or "la EPS").strip() or "la EPS"
    if valor and valor >= 1_000_000:
        return f"🎉 ¡Levantada la glosa de {eps} por ${valor:,.0f}! Excelente defensa."
    return f"✅ ¡Glosa de {eps} levantada! Un pago más asegurado."


def celebrar_racha(dias: int) -> str | None:
    """Mensaje de racha; None si no hay racha destacable (< 3 días)."""
    if dias >= 15:
        return f"🔥 ¡Racha de {dias} días respondiendo glosas! Imparable."
    if dias >= 7:
        return f"💪 Llevás {dias} días seguidos al pie del cañón. ¡Grande!"
    if dias >= 3:
        return f"👏 {dias} días de racha. Se siente el ritmo."
    return None


def celebrar_hito_recuperado(total: float) -> str | None:
    """Hito por monto recuperado acumulado (redondea al hito alcanzado)."""
    hitos = (1_000_000_000, 500_000_000, 100_000_000, 50_000_000, 10_000_000)
    for h in hitos:
        if total >= h:
            return f"🏆 ¡Superaste los ${h:,.0f} defendidos! Tremendo trabajo."
    return None


def mensaje_sin_pendientes() -> str:
    """Cuando el gestor no tiene glosas urgentes."""
    return "😎 Sin glosas urgentes por ahora. ¡Buen momento para adelantar!"
