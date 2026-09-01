"""Qué hacer con cada glosa, en una sola frase que el gestor pueda seguir.

20-08-2026. Yesid, sobre el correo que le llega al gestor cuando recepción sube
el archivo del día: «está muy plana, no explica muy bien». Tenía razón — el
correo decía QUÉ llegó (factura, EPS, valor, vence) pero no QUÉ HACER:

    HUS0000502686 — SEGUROS SURAMERICANA — $213.752 — vence 2026-09-03  AMARILLO

El gestor abre eso y sigue sin saber por dónde empezar, cuál es urgente, cuál
necesita al médico auditor, ni qué responder.

Acá se decide, con los datos que el propio archivo de recepción ya trae:

  · **la prioridad**, que no es solo el semáforo: una ratificada de $5 millones
    que vence en 8 días pesa más que una inicial de $50.000 que vence en 4;
  · **la ruta** — si la glosa es médica hay que trabajarla con el médico
    auditor, y eso hay que decirlo desde el correo, no descubrirlo después;
  · **la respuesta que corresponde** según la familia de la causal;
  · **el aviso de extemporaneidad**, que cambia la defensa por completo;
  · **el texto fijo de la ratificada**, que no hay que ir a buscar a ninguna
    parte: si la glosa es ratificada, va listo para copiar.

Una sola fuente para el correo y para la pantalla: si mañana cambia la regla,
cambia en los dos lados a la vez.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Qué significa cada familia de causal y qué se responde. Los códigos son los
# del Manual Único de Glosas (Res. 2284/2023): las dos primeras letras mandan.
_FAMILIAS: dict[str, tuple[str, str]] = {
    "FA": ("Facturación", "Verificar el cobro contra la factura y los RIPS."),
    "TA": (
        "Tarifas",
        "Comparar el valor cobrado contra la tarifa pactada del contrato "
        "vigente. Si no hay contrato, contra el SOAT del año de la atención.",
    ),
    "SO": (
        "Soportes",
        "Relacionar los soportes que SÍ están en el expediente. Nunca nombrar "
        "uno que no esté: si la EPS lo verifica y falta, ratifica la glosa.",
    ),
    "AU": ("Autorizaciones", "Anexar la autorización o probar que fue urgencia vital."),
    "CO": ("Cobertura", "Acreditar que el servicio está cubierto para ese usuario."),
    "CL": (
        "Calidad / pertinencia",
        "Requiere criterio clínico: la historia clínica sustenta la conducta.",
    ),
    "PE": ("Pertinencia médica", "Requiere criterio clínico del médico auditor."),
    "DE": ("Devolución", "Revisar si procede la devolución o si hay que reexpedir."),
}

# Familias que no se responden sin médico auditor.
_FAMILIAS_MEDICAS = {"CL", "PE"}

# Palabras del campo TIPO GLOSA del archivo de recepción que implican médico.
_TIPOS_MEDICOS = ("MEDIC", "PERTINEN", "CLINIC", "MIXTA")


@dataclass
class PlanDeTrabajo:
    """Lo que el gestor necesita saber de una glosa, ya masticado."""

    prioridad: int = 3  # 1 = primero
    urgencia: str = "NORMAL"  # VENCIDA / HOY / URGENTE / PRONTO / NORMAL
    titular: str = ""  # la frase de una línea
    ruta: str = ""  # cómo se trabaja
    respuesta_sugerida: str = ""  # qué responder
    avisos: list[str] = field(default_factory=list)  # lo que puede costar plata
    con_medico: bool = False
    texto_listo: str = ""  # para pegar (solo ratificadas)
    familia: str = ""


def familia_de(codigo: str | None) -> str:
    """«CL0801» → «CL». Cadena vacía si no se reconoce."""
    cod = (codigo or "").strip().upper()
    return cod[:2] if len(cod) >= 2 and cod[:2] in _FAMILIAS else ""


def _urgencia(dias) -> tuple[str, int]:
    if dias is None:
        return "NORMAL", 3
    try:
        d = int(dias)
    except (TypeError, ValueError):
        return "NORMAL", 3
    if d < 0:
        return "VENCIDA", 0
    if d == 0:
        return "HOY", 0
    if d <= 5:
        return "URGENTE", 1
    if d <= 10:
        return "PRONTO", 2
    return "NORMAL", 3


def _es_medica(tipo_glosa: str | None, familia: str) -> bool:
    if familia in _FAMILIAS_MEDICAS:
        return True
    t = (tipo_glosa or "").strip().upper()
    return any(p in t for p in _TIPOS_MEDICOS)


def construir_plan(
    *,
    codigo_glosa: str | None = None,
    tipo_glosa: str | None = None,
    dias_restantes=None,
    dias_radicacion=None,
    ratificada: bool = False,
    extemporanea: bool = False,
    valor_objetado: float | None = None,
    profesional_medico: str | None = None,
    texto_ratificada: str = "",
) -> PlanDeTrabajo:
    """Arma el plan de una glosa a partir de lo que trae el archivo."""
    fam = familia_de(codigo_glosa)
    nombre_fam, como = _FAMILIAS.get(fam, ("Sin clasificar", "Revisar el detalle de la causal."))
    urgencia, prioridad = _urgencia(dias_restantes)
    plan = PlanDeTrabajo(
        prioridad=prioridad, urgencia=urgencia, familia=fam, respuesta_sugerida=como
    )

    # Las ratificadas pesan más: es la segunda vuelta y lo que sigue es la
    # Superintendencia. Y su texto va listo para copiar.
    if ratificada:
        plan.prioridad = min(plan.prioridad, 1)
        plan.avisos.append(
            "RATIFICADA — es la segunda vuelta. Se mantiene la respuesta inicial y "
            "se pide conciliación. Si no hay acuerdo, va a la Superintendencia."
        )
        plan.texto_listo = texto_ratificada or ""
        plan.respuesta_sugerida = "Texto fijo de ratificada (abajo, listo para copiar)."

    if extemporanea:
        plan.prioridad = min(plan.prioridad, 1)
        plan.avisos.append(
            "EXTEMPORÁNEA — la EPS notificó fuera del plazo del Art. 57 de la Ley "
            "1438/2011. Alegarlo PRIMERO: es defensa de forma y no depende del fondo."
        )

    # Radicación vs. notificación: es el dato que sustenta la extemporaneidad.
    if dias_radicacion is not None:
        try:
            d = int(dias_radicacion)
            if d > 0:
                plan.avisos.append(
                    f"La EPS se tomó {d} días entre la radicación de la factura y "
                    "la notificación de la glosa. Ese número va en la respuesta."
                )
        except (TypeError, ValueError):
            pass

    plan.con_medico = _es_medica(tipo_glosa, fam)
    if plan.con_medico:
        medico = (profesional_medico or "").strip()
        plan.ruta = (
            f"CON EL MÉDICO AUDITOR{' — ' + medico if medico else ''}. "
            "No se responde solo desde cartera: la defensa se sostiene en la "
            "historia clínica y necesita criterio clínico."
        )
    else:
        plan.ruta = "Se trabaja desde cartera: es administrativa/técnica."

    # Plata: por encima de cinco millones se mira antes, pase lo que pase.
    try:
        if valor_objetado and float(valor_objetado) >= 5_000_000:
            plan.prioridad = min(plan.prioridad, 1)
            plan.avisos.append("Más de $5.000.000 en juego.")
    except (TypeError, ValueError):
        pass

    partes = [nombre_fam if fam else "Causal por clasificar"]
    if ratificada:
        partes.append("RATIFICADA")
    if extemporanea:
        partes.append("EXTEMPORÁNEA")
    if plan.con_medico:
        partes.append("con médico auditor")
    plan.titular = " · ".join(partes)
    return plan
